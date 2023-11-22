# speedtest\_ssh
A simple tool for a quick and easy speedtest between two machines via ssh

# Usage

This tool will attempt to use the `ssh` config in `~/.ssh/config` for fields not provided.
```bash
$ speedtest_ssh --help
usage: speedtest_ssh [-h] [--version] [-u USERNAME] [--password PASSWORD] [--port PORT] [--max_seconds MAX_SECONDS] host

positional arguments:
  host                  The host to speedtest the conection to

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -u USERNAME, --username USERNAME
                        The username to use to ssh
  --password PASSWORD   The password to use to ssh
  --port PORT           The port to use to ssh
  --max_seconds MAX_SECONDS
                        A soft limit for how many seconds to spend uploading / downloading
```
