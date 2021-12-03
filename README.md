# NetBox DNS Handler

This project aims to handle all the configuration on a NetBox into a PowerDNS
service (through its database).

My focus is on my internal network. Maybe the script and general design could
be used for public-facing IPs, but that's outside my scope. Pull requests are
welcome, as long as they don't break my use case.

Anyone may benefit from using this project under the following assumptions:

- You are using (or decide to use) [NetBox](https://netbox.readthedocs.io/en/stable/).
- You have properly populated certain fields on the IPs and DNS names on NetBox.
- You can use PowerDNS (SQLite backend) as a name server for your internal network.

This project has a certain focus on IPv6 and hardware address. If you are using
SLAAC on your internal network, then this project will probably help you manage
the burden of maintaining your IPv6 addresses.

At the time being, I am the sole user of this project. This means that there are
certain hardcoded variables here and there (e.g. the `DNS_ROOT_DOMAIN` or the 
`DNS_SUBDOMAINS`). I may fix that and improve the code in order to add flexibility,
but that will happen either when I have the need or when somebody proposes a PR
fixing that. I may do it anyways if anybody is interested.

## Use flow

**This is not a quickstart**. There are variables that should be changed,
hardcoded values that must be tweaked, and configuration to be done. Once
that has been said and done, the basic steps in order to use this script
are the following:

- Prepare the Python virtual environment, use the `requirements.txt`.
- Export the variables `NETBOX_TOKEN`, `NETBOX_API`, `NBDNSH_SQLITE3_FILE`.
- Run `nbdnsh.py`.
- This should update the sqlite file (for PowerDNS).
- If you are not running the script in-place, sync the database.
- Restart dnsmasq. AFAICT, PowerDNS restart is only required if you have
manually moved databases instead of performing changes in-place.

## Automatization

I have envisioned two main ways to automatically rerun this script and update
DNS data:

### Use of NetBox Webhooks

The [webhooks feature](https://netbox.readthedocs.io/en/stable/additional-features/webhooks/)
allows NetBox to inform to a remote system that there has been a certain event
or trigger.

Potentially, by using webhooks, we could configure partial updates or more
fine-grain mechanisms. This is something that may be required for huge
deployments with potentially thousands of IP. However, this would also increase
the complexity of the NBdnsH project, and thus it remains out of the scope of
this project (at least for now).

### Perform polling

You can execute this script periodically (e.g. each hour) and use that. The
polling may be inefficient, but it is a simple way to make everything works and
requires zero additional configuration on the NetBox side.
