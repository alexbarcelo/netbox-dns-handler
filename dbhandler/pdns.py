from ipaddress import IPv4Address, IPv6Address, ip_interface
import sqlite3
from typing import Union


class PdnsDBHandler:
    DNS_TTL = 3600
    DNS_PRIO = 0

    SRV_WEIGHT = 1

    def __init__(self, sqlite_path, root_domain):
        self._con = sqlite3.connect(sqlite_path)
        self._con.row_factory = sqlite3.Row

        # Store this
        self.root_domain = root_domain
        self.root_domain_id = -1

        # And proceed to query and cache the domain ids.
        # This dictionary has keys as `.subdomain.` and integers as values.
        self._subdomain_ids = dict()

        for subdomain_row in self._con.execute("SELECT id, name FROM domains"):
            domain_name = subdomain_row["name"]
            if not domain_name.endswith(root_domain):
                print(f"Ignoring entry `{ domain_name }`")
                continue

            if domain_name == root_domain:
                self.root_domain_id =  subdomain_row["id"]
            else:
                subdomain = domain_name[:-len(root_domain)]

                # Build the basic structure for interfacing the database and the domains
                self._subdomain_ids[f".{ subdomain }"] =  subdomain_row["id"]

    def dns_name_to_domain_id(self, dns_name):
        if not dns_name.endswith(self.root_domain):
            raise ValueError(f"The DNS entry `{ dns_name }` is not part of root domain `{ self.root_domain }`")
        
        prefix_name = dns_name[:-len(self.root_domain)]

        for subdomain, domain_id in self._subdomain_ids.items():
            if prefix_name.endswith(subdomain):
                return domain_id
        
        # No subdomain found, so that implies that it is for root
        return self.root_domain_id

    def cleanup_addresses(self, all_entries):
        """Given all valid entries, remove the extraneous ones.
        
        All valid entries is given as a set of tuples (ip_interface, dns_name).
        """
        cur = self._con.cursor()
        cur.execute("SELECT * FROM records WHERE type IN ('A', 'AAAA')")

        remove_ids = list()
        for row in cur:
            dns_name = row["name"]
            address = row["content"]
            ip = ip_interface(address).ip

            if (ip, dns_name) not in all_entries:
                print(f"Adding { dns_name }@{ address } to the list of records to eliminate")
                remove_ids.append((str(row["id"]),))

        print(f"Ready to eliminate #{ len(remove_ids) } records.")
        cur.executemany("DELETE FROM records WHERE id IS ?", remove_ids)
        self._con.commit()

    def _put_or_update(self, ipaddr: Union[IPv4Address, IPv6Address], dns_name):
        if not dns_name.endswith(".%s" % self.root_domain):
            print("WARNING: I do not know the domain of `%s`, ignoring" % dns_name)
            return

        record_type = "AAAA" if isinstance(ipaddr, IPv6Address) else "A"

        cur = self._con.execute(
            "SELECT * FROM records WHERE name=:name AND type=:type AND content=:content",
            {"name": dns_name, "type": record_type, "content": str(ipaddr)}
        )
        
        entry = cur.fetchone()

        if entry:
            if entry["content"] != str(ipaddr):
                print(f"Record { record_type } for { dns_name } exists and is outdated, updating")
                cur.execute("UPDATE records SET content=:content WHERE id=:id",
                            {"id": entry["id"], "content": str(ipaddr)})
            else:
                print(f"Record { record_type } for { dns_name } exists and is valid")
        else:
            print(f"Creating record { record_type } for { dns_name }")
            
            domain_id = self.dns_name_to_domain_id(dns_name)
            cur.execute("INSERT INTO records (domain_id, name, type, content, ttl, prio) "\
                        "VALUES (:domain_id, :name, :type, :content, :ttl, :prio)",
                        {
                            "domain_id": domain_id,
                            "type": record_type,
                            "name": dns_name,
                            "content": str(ipaddr),
                            "ttl": self.DNS_TTL,
                            "prio": self.DNS_PRIO,
                        })

    def populate_ips(self, entries):
        """Given a list of `entries` (from NetBox), populate the A and AAAA records."""

        for ip_addr in entries:
            ip = ip_interface(ip_addr.address).ip

            if not ip_addr.dns_name:
                print(f"WARNING: Ignoring the following IP because it doesn't have a DNS name: { ip }")
                ass_obj = ip_addr.assigned_object
                if not ass_obj:
                    print("WARNING: It has no assigned object at all")
                elif hasattr(ass_obj, "device"):
                    print("WARNING: The device is: %s @ %s" %
                        (ass_obj.device.display, ass_obj.device.url))
                elif hasattr(ass_obj, "virtual_machine"):
                    print("WARNING: The VM is: %s @ %s" %
                        (ass_obj.virtual_machine.display, ass_obj.virtual_machine.url))
                else:
                    print("WARNING: The assigned object is unkown, here: %s" % (ass_obj.url))
                continue

            self._put_or_update(ip,  ip_addr.dns_name)

        self._con.commit()

    def populate_srv(self, nb_entries, record_name):
        """Given a list of `entries` (from NetBox), populate the SRV entries to a certain record name."""
        db_items = list()

        cur = self._con.cursor()

        for entry in nb_entries:
            try:
                dns_name = entry.ipaddresses[0].dns_name
            except IndexError:
                print(f"Could not get an assigned IP for { entry } ({ entry.url })")
                continue

            record_content = f"{ self.SRV_WEIGHT } { entry.ports[0] } { dns_name }"

            cur.execute("SELECT * FROM records WHERE name=:name AND type='SRV' AND content like :content",
                        {"name": record_name, "content": f"%{ dns_name }"})

            dns_entry = cur.fetchone()

            if dns_entry:
                print(f"Found entry for service { dns_name }@{ record_name }, checking...")
                # Check if the content is valid already
                if dns_entry["content"] != record_content:
                    print(f"Updating, values\n\tPrev content: { dns_entry['content'] }\n\tNext content: { record_content }")
                    cur.execute("UPDATE records SET content=:content WHERE id=:id",
                                {"id": dns_entry["id"], "content": record_content})
                else:
                    # Nothing to do if the content matches
                    print("Valid content")
            else:
                # new record
                print(f"Creating new entry { dns_name }@{ record_name }")
                cur.execute("INSERT INTO records(domain_id, name, type, content, ttl, prio) "
                            "VALUES (:domain_id, :name, :type, :content, :ttl, :prio)",
                            {
                                "domain_id": self.dns_name_to_domain_id(record_content),
                                "name": record_name,
                                "type": "SRV",
                                "content": record_content,
                                "ttl": self.DNS_TTL,
                                "prio": self.DNS_PRIO,
                            })

        self._con.commit()
