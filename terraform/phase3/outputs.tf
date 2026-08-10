output "lightning_hosts" {
  description = "One per corridor region. Index matches harness/topology.py host_index."
  value = [
    for i, inst in google_compute_instance.lightning : {
      name       = inst.name
      corridor   = var.regions[i].role
      zone       = var.regions[i].zone
      private_ip = inst.network_interface[0].network_ip
      public_ip  = inst.network_interface[0].access_config[0].nat_ip
    }
  ]
}

output "generator" {
  value = {
    name      = google_compute_instance.generator.name
    zone      = local.generator_zone
    public_ip = google_compute_instance.generator.network_interface[0].access_config[0].nat_ip
  }
}

output "next_steps" {
  description = "Ordering matters -- each step gates the next."
  value       = <<-EOT
    1. ./scripts/deploy_lightning.sh          create wallets, collect macaroons
    2. python scripts/lightning_bootstrap.py  fund and open the topology
    3. ./scripts/inject_impairment.sh         realism technique #2, same profile as phase 2
    4. harness run --config config/phase3.json --tps 10 --amount 200
       ^ ONE low-rate run first. Phase 2's lesson: confirm the pipeline before
         spending cluster hours on a sweep that may be measuring our own bug.
  EOT
}
