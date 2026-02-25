variable "subscription_id" {
  type = string
  sensitive = true
}

variable "location" {
  type    = string
  default = "EastUS2"
}

variable "gh_repo" {
  type = string
}

variable "COPILOTSTUDIOAGENT__ENVIRONMENTID" {
  type = string
}

variable "COPILOTSTUDIOAGENT__SCHEMANAME" {
  type = string
}

variable "COPILOTSTUDIOAGENT__AGENTAPPID" {
  type = string
}

variable "COPILOTSTUDIOAGENT__CLIENTSECRET" {
  type = string
  sensitive = true
}