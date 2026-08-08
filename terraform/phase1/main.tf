/**
 * Phase 1 infrastructure: one region, one small Polygon Edge cluster.
 *
 * Purpose is to prove the pipeline works end to end and to produce a real
 * per-hour cost figure. It produces no data for the paper.
 *
 * Everything here is destroyed with `tofu destroy`. That single command
 * removing *everything* is the reason this is OpenTofu rather than shell
 * scripts -- hand-rolled scripts leak disks and addresses that keep billing
 * silently, which across multiple regions is the most likely way to waste
 * real money on this project.
 *
 * Cost when running: roughly $0.60-0.80/hour on spot pricing for the default
 * 4-validator setup. Cost when destroyed: zero.
 */

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# ---------------------------------------------------------------------------
# Network
#
# Deliberately no Cloud NAT. A NAT gateway bills by the hour whether or not
# anything is running, and across four regions in later phases that alone
# would be a meaningful share of the budget. Instances get public addresses
# instead, locked down by the firewall rules below.
# ---------------------------------------------------------------------------

resource "google_compute_network" "bench" {
  name                    = "remittance-bench-p1"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "bench" {
  name          = "remittance-bench-p1-${var.region}"
  ip_cidr_range = "10.10.0.0/16"
  region        = var.region
  network       = google_compute_network.bench.id
}

# Consensus traffic between validators. Open internally, since this is the
# traffic whose real cross-region latency we are trying to measure later.
resource "google_compute_firewall" "internal" {
  name     = "remittance-bench-p1-internal"
  network  = google_compute_network.bench.name
  priority = 1000

  allow {
    protocol = "tcp"
    ports    = ["1478", "8545", "9632"]
  }
  allow { protocol = "udp" }
  allow { protocol = "icmp" }

  source_ranges = ["10.10.0.0/16"]
}

# SSH and RPC, restricted to the operator. Never 0.0.0.0/0 -- an open RPC port
# on a machine holding chain keys is found by scanners within hours.
resource "google_compute_firewall" "operator" {
  name     = "remittance-bench-p1-operator"
  network  = google_compute_network.bench.name
  priority = 1000

  allow {
    protocol = "tcp"
    ports    = ["22", "8545"]
  }

  source_ranges = [var.operator_ip_cidr]
}

# ---------------------------------------------------------------------------
# Shutdown guards
#
# Injected into every machine. The hard timer is armed before anything else
# runs, so even a startup script that crashes still leaves a cluster that
# switches itself off.
# ---------------------------------------------------------------------------

locals {
  shutdown_guard = templatefile("${path.module}/scripts/shutdown_guard.sh", {
    max_lifetime_minutes  = var.max_lifetime_minutes
    idle_shutdown_minutes = var.idle_shutdown_minutes
  })

  validator_startup = join("\n", [
    local.shutdown_guard,
    templatefile("${path.module}/scripts/validator_setup.sh", {
      chain_id     = var.chain_id
      edge_version = var.edge_version
    }),
  ])

  generator_startup = join("\n", [
    local.shutdown_guard,
    file("${path.module}/scripts/generator_setup.sh"),
  ])

  spot_scheduling = var.use_spot ? {
    provisioning_model          = "SPOT"
    preemptible                 = true
    automatic_restart           = false
    on_host_maintenance         = "TERMINATE"
    instance_termination_action = "STOP"
    } : {
    provisioning_model          = "STANDARD"
    preemptible                 = false
    automatic_restart           = true
    on_host_maintenance         = "MIGRATE"
    instance_termination_action = null
  }
}

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

resource "google_compute_instance" "validator" {
  count        = var.validator_count
  name         = "bench-p1-validator-${count.index}"
  machine_type = var.machine_type
  zone         = var.zone
  labels       = merge(var.labels, { role = "validator" })

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.bench.id
    access_config {}
  }

  scheduling {
    provisioning_model          = local.spot_scheduling.provisioning_model
    preemptible                 = local.spot_scheduling.preemptible
    automatic_restart           = local.spot_scheduling.automatic_restart
    on_host_maintenance         = local.spot_scheduling.on_host_maintenance
    instance_termination_action = local.spot_scheduling.instance_termination_action
  }

  metadata = {
    startup-script  = local.validator_startup
    validator-index = tostring(count.index)
    validator-count = tostring(var.validator_count)
  }

  # Read-only. These machines never need to modify cloud resources; if one is
  # compromised, the credential it carries can't be used to spin anything up.
  service_account {
    scopes = ["https://www.googleapis.com/auth/devstorage.read_only",
    "https://www.googleapis.com/auth/logging.write"]
  }

  allow_stopping_for_update = true
}

# ---------------------------------------------------------------------------
# Load generator
# ---------------------------------------------------------------------------

resource "google_compute_instance" "generator" {
  name         = "bench-p1-generator"
  machine_type = var.generator_machine_type
  zone         = var.zone
  labels       = merge(var.labels, { role = "generator" })

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 50
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.bench.id
    access_config {}
  }

  scheduling {
    provisioning_model          = local.spot_scheduling.provisioning_model
    preemptible                 = local.spot_scheduling.preemptible
    automatic_restart           = local.spot_scheduling.automatic_restart
    on_host_maintenance         = local.spot_scheduling.on_host_maintenance
    instance_termination_action = local.spot_scheduling.instance_termination_action
  }

  metadata = {
    startup-script = local.generator_startup
  }

  service_account {
    scopes = ["https://www.googleapis.com/auth/devstorage.read_only",
    "https://www.googleapis.com/auth/logging.write"]
  }

  allow_stopping_for_update = true
}
