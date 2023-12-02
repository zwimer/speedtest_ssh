# speedtest\_ssh
A simple tool for a quick and easy speedtest between two machines using ssh

# Usage

This tool will attempt to use the `ssh` config in `~/.ssh/config` for fields not provided.
```bash
usage: speedtest-ssh [-h] [--version] [-u USERNAME] [--password PASSWORD]
                     [--port PORT] [--num_seconds NUM_SECONDS]
                     [-m {rsync,sftp}]
                     host

positional arguments:
  host                  The host to speedtest the conection to

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -u USERNAME, --username USERNAME
                        The username to use to ssh
  --password PASSWORD   The password to use to ssh
  --port PORT           The port to use to ssh
  --num_seconds NUM_SECONDS
                        An approximate amount of time this test should take
  -m {rsync,sftp}, --mode {rsync,sftp}
                        The speedtest method. Defaults to rsync
```

# Notes

1. This will be subject to your disk read/write speed in `/tmp` on both devices
