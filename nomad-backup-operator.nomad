job "nomad-backup-operator" {
  region      = "global"
  datacenters = ["dc1"]

  type = "service"

  group "nomad-backup-operator" {
    network {
      # we only need to communicate with the nomad socket
      mode = "none"
    }

    service {
      name = "nomad-backup-operator"
    }

    task "nomad-backup-operator" {
      driver = "docker"

      config {
        image = "docker.io/jaub/nomad-backup-operator:0.0.3"

        # if we're already running as a regular user it's not really needed but
        # doesn't hurt
        cap_drop = ["all"]

        security_opt = [
          # weird that this isn't the default
          "no-new-privileges=true",
          "seccomp=/etc/nomad/seccomp.json",
        ]

      }

      template {
        # load nomad token
        data = <<EOF
{% raw %}
{{ if nomadVarExists "nomad/jobs/nomad-backup-operator" }}
{{- with nomadVar "nomad/jobs/nomad-backup-operator" }}
{{- range $kk, $vv := . }}
{{ $kk }}={{ $vv }}
{{- end }}
{{- end }}
{{- end }}
{% endraw %}
EOF
        # a destination is always required even though we're just loading into
        # env
        destination = "secrets/env"
        env         = true
      }

      # the template used to create backup jobs
      template {
        # having the backup job template right in the operator job is an eyesore
        data = <<JOB
{{ lookup('ansible.builtin.file', '../jobs/nomad-backup.nomad') }}
JOB
        # change the delimiter to avoid conflicting with jinja delimeters
        # ideally we could disable templating all together but that doesn't seem
        # possible
        left_delimiter = "[["
        right_delimiter = "]]"
        destination = "secrets/template"
      }

      # run as hcluster user
      user = "950:590"

      resources {
        # Both params need tuning. Hopefully with a grafana dashboard that'll be
        # easy
        cpu    = 100
        memory = 100
      }
    }
  }
}
