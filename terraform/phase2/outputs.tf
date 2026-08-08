output "validator_private_ips" {
  description = "Internal addresses. Google's network is global, so validators reach each other on these across regions -- real distance, off the public internet."
  value       = google_compute_instance.validator[*].network_interface[0].network_ip
}

output "validator_public_ips" {
  value = google_compute_instance.validator[*].network_interface[0].access_config[0].nat_ip
}

output "validator_placement" {
  description = "Which validator sits in which remittance corridor. Record this alongside results -- geography is the independent variable in this phase."
  value = [
    for i, r in var.regions :
    "validator-${i}: ${r.region} (${r.role}) ${google_compute_instance.validator[i].network_interface[0].network_ip}"
  ]
}

output "generator_public_ip" {
  value = google_compute_instance.generator.network_interface[0].access_config[0].nat_ip
}

output "generator_zone" {
  value = local.generator_zone
}

output "zone" {
  description = "Zone of validator 0. Kept for compatibility with the bootstrap script."
  value       = var.regions[0].zone
}

output "validator_zones" {
  description = "Per-validator zones. Unlike Phase 1, these differ, so any script reaching a specific machine must use the matching zone."
  value       = [for r in var.regions : r.zone]
}

output "rpc_url" {
  description = "Chain endpoint the harness submits to. Deliberately the validator co-located with the generator, so submission cost stays constant while consensus pays the cross-region price."
  value       = "http://${google_compute_instance.validator[var.generator_region_index].network_interface[0].network_ip}:8545"
}

output "chain_id" {
  value = var.chain_id
}

output "shutdown_guards" {
  value = format(
    "hard shutdown at +%d minutes; idle shutdown after %d minutes without benchmark activity",
    var.max_lifetime_minutes, var.idle_shutdown_minutes,
  )
}

output "estimated_hourly_cost_usd" {
  description = "Rough guide only. Excludes cross-region data transfer, which is new in this phase and is the main cost difference from Phase 1."
  value = format(
    "~$%.2f/hour compute (%d validators + generator, %s) plus cross-region transfer",
    var.use_spot ? (length(var.regions) * 0.043 + 0.043) : (length(var.regions) * 0.19 + 0.19),
    length(var.regions),
    var.use_spot ? "spot" : "on-demand",
  )
}

output "next_steps" {
  value = <<-EOT

    Multi-region cluster is up. Nothing is running on it yet.

      1. Start the chain across all regions:
           ./scripts/bootstrap_cluster.sh --phase phase2

      2. Put the harness on the generator (in-region, not your laptop):
           ./scripts/deploy_harness.sh --phase phase2

      3. Deploy the test dollar and fund wallets, then run the load ramp.

    EXPECT WORSE NUMBERS THAN PHASE 1. That is the point. Consensus now waits
    on messages crossing oceans instead of a datacentre floor. Settlement
    latency should rise from ~3s toward the round-trip time between regions,
    and the throughput ceiling should fall. That degradation is the finding.

    WHEN FINISHED: `tofu destroy`. The shutdown timers stop the machines but
    leave the disks, which keep billing.
  EOT
}
