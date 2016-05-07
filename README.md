# accurev-git-migrate

**A Python 2.7 script which automatically migrates stream history from AccuRev into a Git branch.**

### Usage instructions:

To start the script simply run

`python migrate.py accurevBranch repoLocation`

The script will then get the AccuRev branch history and transition it into the specified git repository.

The script also offers the option to append history to an already performed migration by running with the `-a` flag.

The arguments the script uses are as follows, also displayed by running `python migrate.py -h`:

|         Argument           |                          Description                            |
| ---------------------------|-----------------------------------------------------------------|
| accurevBranch              |            name of AccuRev branch to be transitioned            |
| repoLocation               |          path to folder in which to transition                  |
| -a, --append               | append new AccuRev branch history to an existing git repository |
