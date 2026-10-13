variable "aws_region" {
  description = "AWS region for every resource."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name, used as a prefix for resource names."
  type        = string
  default     = "globant-challenge"
}

variable "environment" {
  description = "Deployment environment (dev, prod...)."
  type        = string
  default     = "dev"
}

# --- Network ---

variable "vpc_cidr" {
  description = "CIDR block of the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "availability_zone_count" {
  description = "Number of availability zones for the private subnets (Aurora needs at least 2)."
  type        = number
  default     = 2

  validation {
    condition     = var.availability_zone_count >= 2 && var.availability_zone_count <= 3
    error_message = "Use 2 or 3 availability zones."
  }
}

# --- Database ---

variable "db_engine_version" {
  description = "Aurora PostgreSQL version (16.3+ supports scaling to 0 ACU)."
  type        = string
  default     = "16.6"
}

variable "db_name" {
  description = "Initial database name."
  type        = string
  default     = "globant"
}

variable "db_master_username" {
  description = "Master user; its password is generated and stored by RDS in Secrets Manager."
  type        = string
  default     = "postgres_admin"
}

variable "db_min_capacity" {
  description = "Minimum Aurora capacity in ACUs. 0 enables auto-pause (dev); use 0.5+ in prod."
  type        = number
  default     = 0
}

variable "db_max_capacity" {
  description = "Maximum Aurora capacity in ACUs."
  type        = number
  default     = 4
}

variable "db_seconds_until_auto_pause" {
  description = "Idle seconds before Aurora pauses (only when db_min_capacity is 0)."
  type        = number
  default     = 900
}

variable "db_instance_count" {
  description = "Aurora instances: 1 for dev, 2+ for a Multi-AZ reader/failover."
  type        = number
  default     = 1
}

variable "db_backup_retention_days" {
  description = "Automated backup retention in days."
  type        = number
  default     = 7
}

variable "deletion_protection" {
  description = "Protect the database and keep a final snapshot on destroy (enable in prod)."
  type        = bool
  default     = false
}

# --- Storage and ingestion ---

variable "force_destroy_bucket" {
  description = "Allow `terraform destroy` to delete a non-empty raw bucket (dev only)."
  type        = bool
  default     = true
}

variable "landing_transition_days" {
  description = "Days before raw files in landing/ move to S3 Standard-IA."
  type        = number
  default     = 30
}

variable "loader_timeout_seconds" {
  description = "Timeout of the loader Lambda; also drives the SQS visibility timeout."
  type        = number
  default     = 900
}

variable "loader_max_receive_count" {
  description = "Delivery attempts before a message is moved to the DLQ."
  type        = number
  default     = 3
}
