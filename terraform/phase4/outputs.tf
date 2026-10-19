output "validators" {
  description = "Two per corridor region. Index 0 is the boot node at 10.40.0.10."
  value = [
    for i, inst in google_compute_instance.validator : {
      name       = inst.name
      corridor   = local.validators[i].role
      zone       = local.validators[i].zone
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

output "shard_config" {
  description = "Must match expected_shards in harness/adapters/near.py."
  value = {
    num_shards           = var.num_shards
    validators           = length(local.validators)
    validators_per_shard = length(local.validators) / var.num_shards
  }
}

output "next_steps" {
  value = <<-EOT
    1. ./scripts/deploy_near.sh
         builds ONE genesis pinning ${var.num_shards} shards and all
         ${length(local.validators)} validators, distributes it, starts the chain,
         deploys the NEP-141 token, funds senders, registers recipients
    2. harness run --config config/phase4.json --tps 10 --amount 200
         ONE low-rate run first. The adapter's health check refuses to run
         below ${var.num_shards} shards -- if it fires, the chain is not sharded
         and no measurement from it would mean anything.
  EOT
}
