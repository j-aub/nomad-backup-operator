when a new job is deployed,

if backup_cron and backup_volume meta options are set we'll deploy a backup job

when a job is destroyed,

destroy job_name_backup

# example nomad-backup-operator nomad job

An example nomad-backup template is provided in nomad-backup.nomad

A full nomad-backup-operator-backup job can be found in
nomad-backup-operator.nomad

# needed ACLs

## list-jobs 

iterating through list of jobs on initial start to find jobs that potentially need backup jobs

## read-job

we need to read all jobs to get their meta blocks

## submit-job

submitting backup jobs

## storage permissions

The operator needs to have rw access to all of the repository volumes and ro/rw
access the the volumes getting backed up. This depends on how the backup works.
For example if you need to dump a database you'd need rw access but for simple
snapshotting ro suffices.

read more about ACLs for host volumes here:
https://developer.hashicorp.com/nomad/tutorials/access-control/access-control-policies
