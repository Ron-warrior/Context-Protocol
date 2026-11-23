# Runbook

## Writes are failing

Check the free space on the volume holding the store first. If the store cannot
be parsed, do not overwrite it: move it aside, restore the last good copy, and
only then restart the writer.

If the volume is full, freeze the writer until space is reclaimed. Accepting
writes that will fail loses data that a clean rejection would have kept.

## Sessions are all expiring early

Compare the server clock against the issue timestamps. A clock skew larger than
the TTL makes every session look expired the moment it is created.
