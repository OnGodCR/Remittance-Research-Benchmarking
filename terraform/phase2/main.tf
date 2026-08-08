/**
 * Phase 2, step 1: multi-region deployment (realism technique #1).
 *
 * The ONLY change from Phase 1 is geography. Same machine sizes, same node
 * count, same everything else -- because the phased rollout exists so that
 * when a result moves, the cause is unambiguous. Changing hardware and
 * geography together would make it impossible to attribute the difference.
 *
 * What this buys: consensus now pays real intercontinental latency. Four
 * validators sit in Virginia, Mumbai, Singapore and London, so every round of
 * agreement waits on messages crossing oceans -- roughly 200-250ms Virginia
 * to Mumbai, against the 0.165ms measured inside a single datacentre in
 * Phase 1. Throughput and settlement latency are both expected to worsen
 * substantially, and that degradation IS the finding.
 *
 * One thing that makes this workable: Google's virtual network is global, so
 * validators in different regions still reach each other on internal
 * addresses. Traffic stays off the public internet while still travelling the
 * real physical distance. It does incur cross-region transfer charges, which
 * is the main cost difference from Phase 1.
 *
 * Destroy with `tofu destroy`. That single command removing everything is why
 * this is infrastructure-as-code rather than shell scripts -- across four
 * regions, orphaned disks and addresses are the likeliest way to waste money.
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
  region  = var.regions[0].region
  zone    = var.regions[0].zone
}

locals {
  # One /24 per region, all inside 10.20.0.0/16 so a single firewall rule
  # covers internal traffic no matter how many regions are added.
  subnet_cidrs = { for i, r in var.regions : r.region => cidrsubnet("10.20.0.0/16", 8, i) }

  shutdown_guard = templatefile("${path.module}/../phase1/scripts/shutdown_guard.sh", {
    max_lifetime_minutes  = var.max_lifetime_minutes
    idle_shutdown_minutes = var.idle_shutdown_minutes
  })

  validator_startup = join("\n", [
    local.shutdown_guard,
    templatefile("${path.module}/../phase1/scripts/validator_setup.sh", {
      chain_id     = var.chain_id
      edge_version = var.edge_version
    }),
  ])

  generator_startup = join("\n", [
    local.shutdown_guard,
    file("${path.module}/../phase1/scripts/generator_setup.sh"),
  ])

  spot = var.use_spot ? {
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

  generator_zone   = var.regions[var.generator_region_index].zone
  generator_region = var.regions[var.generator_region_index].region
}

# ---------------------------------------------------------------------------
# Network -- one global network, one subnet per region
# ---------------------------------------------------------------------------

resource "google_compute_network" "bench" {
  name                    = "remittance-bench-p2"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "bench" {
  for_each      = local.subnet_cidrs
  name          = "remittance-bench-p2-${each.key}"
  ip_cidr_range = each.value
  region        = each.key
  network       = google_compute_network.bench.id
}

# Consensus traffic between validators, across regions. This is the traffic
# whose real latency the whole phase exists to introduce.
resource "google_compute_firewall" "internal" {
  name     = "remittance-bench-p2-internal"
  network  = google_compute_network.bench.name
  priority = 1000

  allow {
    protocol = "tcp"
    ports    = ["1478", "8545", "9632"]
  }
  allow { protocol = "udp" }
  allow { protocol = "icmp" }

  source_ranges = ["10.20.0.0/16"]
}

# SSH and chain access, restricted to the operator. Never open to the world --
# an exposed chain endpoint is found by scanners within hours.
resource "google_compute_firewall" "operator" {
  name     = "remittance-bench-p2-operator"
  network  = google_compute_network.bench.name
  priority = 1000

  allow {
    protocol = "tcp"
    ports    = ["22", "8545"]
  }

  source_ranges = [var.operator_ip_cidr]
}

# ---------------------------------------------------------------------------
# Validators -- one per region
# ---------------------------------------------------------------------------

resource "google_compute_instance" "validator" {
  count        = length(var.regions)
  name         = "bench-p2-validator-${count.index}"
  machine_type = var.machine_type
  zone         = var.regions[count.index].zone

  labels = merge(var.labels, {
    role   = "validator"
    corner = replace(lower(var.regions[count.index].role), " ", "-")
  })

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.bench[var.regions[count.index].region].id
    access_config {}
  }

  scheduling {
    provisioning_model          = local.spot.provisioning_model
    preemptible                 = local.spot.preemptible
    automatic_restart           = local.spot.automatic_restart
    on_host_maintenance         = local.spot.on_host_maintenance
    instance_termination_action = local.spot.instance_termination_action
  }

  metadata = {
    startup-script  = local.validator_startup
    validator-index = tostring(count.index)
    corridor-role   = var.regions[count.index].role
  }

  service_account {
    scopes = ["https://www.googleapis.com/auth/devstorage.read_only",
    "https://www.googleapis.com/auth/logging.write"]
  }

  allow_stopping_for_update = true
}

# ---------------------------------------------------------------------------
# Load generator -- fixed region, never moves
# ---------------------------------------------------------------------------

resource "google_compute_instance" "generator" {
  name         = "bench-p2-generator"
  machine_type = var.generator_machine_type
  zone         = local.generator_zone
  labels       = merge(var.labels, { role = "generator" })

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 50
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.bench[local.generator_region].id
    access_config {}
  }

  scheduling {
    provisioning_model          = local.spot.provisioning_model
    preemptible                 = local.spot.preemptible
    automatic_restart           = local.spot.automatic_restart
    on_host_maintenance         = local.spot.on_host_maintenance
    instance_termination_action = local.spot.instance_termination_action
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
