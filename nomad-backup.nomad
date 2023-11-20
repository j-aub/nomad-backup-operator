job "{{ backup_job_id }}" {
  region      = "global"
  datacenters = ["dc1"]

  type = "batch"

  periodic {
    # the cron will be set by the operator
    prohibit_overlap = true
  }

  group "{{ backup_job_id }}" {
    restart {
      # trying a failing backup several times is risky
      attempts = 0
    }

    network {
      mode = "bridge"
    }

    volume "repository" {
      type      = "host"
      read_only = false
      source    = "{{ backup_job_id }}-repository"
    }

    volume "backup" {
      type      = "host"
      read_only = "{{ backup_volume_rw }}"
      source    = "{{ backup_volume }}"
    }

    service {
      name = "{{ backup_job_id }}"

      # connect block will be added here
    }

    task "{{ backup_job_id }}" {
      driver = "docker"

      config {
        image = "docker.io/jaub/nomad-backup:0.1.1"

        
        command = "sleep"
        args    = ["9999999"]
        cap_drop = ["all"]

        security_opt = [
          # weird that this isn't the default
          "no-new-privileges=true",
          "seccomp=/etc/nomad/seccomp.json",
        ]

      }

      identity {
        env = true
      }


      template {
        # load nomad token
        data = <<EOF
# we don't want jinja to mess with nomad templating
{%- raw %}
{{ if nomadVarExists "nomad/jobs/qbittorrent-backup" }}
{{- with nomadVar "nomad/jobs/qbittorrent-backup" }}
{{- range $kk, $vv := . }}
{{ $kk }}={{ $vv }}
{{- end }}
{{- end }}
{{- end }}
{%- endraw %}
EOF
        # a destination is always required even though we're just loading into
        # env
        destination = "secrets/env"
        env         = true
      }

      template {
        # load restic repo password
        data        = <<EOF
{%- raw %}
{{ with nomadVar "nomad-backup" }}{{ .password }}{{ end }}
{%- endraw %}
EOF
        destination = "secrets/password_file"
      }

      volume_mount {
        volume      = "repository"
        destination = "/repository"
        read_only   = false
      }

      volume_mount {
        volume      = "backup"
        destination = "/backup"
        read_only   = false
      }

      # run as hcluster user
      user = "950:950"

      resources {
        # Both params need tuning. Hopefully with a grafana dashboard that'll be
        # easy
        cpu    = 500
        memory = 500
      }
    }
  }
}
