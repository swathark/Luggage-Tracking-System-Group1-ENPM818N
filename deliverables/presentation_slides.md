---
marp: true
theme: default
paginate: true
---

# Global Luggage Logistics & Processing
**Group Project: Serverless Architecture & Highly Available Platforms**
*ENPM818N - Spring 2026*

---

# 🛫 Platform Overview
A modernized **Customer Service Portal** designed to give airport personnel deterministic views over isolated tracking boundaries.

**Core Objectives Achieved:**
1. Secure, 3-Tier Web Architecture mapping to modern DevSecOps layouts.
2. Complete elimination of manual deployment risk via Infrastructure as Code (Terraform).
3. Highly optimized billing paradigms capitalizing intimately on Auto Scaling logic and Single-AZ integrations.

---

# 🏗️ Infrastructural Core
- **Network Boundaries:** Housed efficiently across dual AWS Availability Zones.
- **Compute Isolation:** Frontend routing happens over Public ALBs. The core Python kernels compute deep inside Private Subnets disconnected from direct public interfaces.
- **Database Backend:** Amazon RDS configured for isolated runtime tracking payloads securely locked inside AWS parameter definitions.

---

# 🔐 Security Posture (Zero-Trust)
**Passwords:** Nowhere to be found. 
We leverage Terraform's `random_password` provider to boot the infrastructure securely, locking dynamically generated certificates purely within **AWS Secrets Manager**.

**Encryption Flow:**
- **In-Transit:** Self-signed TLS mapping 443 routes at the public edge boundary.
- **At-Rest:** RDS Database clusters and EC2 Block storage volumes utilize enforced KMS encryption architectures to prevent arbitrary runtime parsing.

---

# ⚡ Serverless Event Architecture
Whenever an agent opens a Customer Escalation framework (e.g. Lost Luggage):
1. **Application** pushes directly to Postgres and fans the notification horizontally toward **Amazon SNS**.
2. **SNS** triggers an active payload sequence straight down into an **Amazon SQS** messaging buffer.
3. Automatically, an **AWS Lambda Python Processor** parses the queue and executes automated analytics mapping, generating zero ambient polling costs along the way.

---

# 📡 Observability & Logs
Complete integration of auditing fabrics ensures any security footprint within the VPC triggers forensics.
- ALB Access Logs mapping straight down to partitioned S3 buckets.
- CloudTrail enforcing system-wide API observability.
- CloudWatch Alarms enforcing strict CPU metric boundaries.

---

# 👥 Project Roles & Collaboration
- **Student 1 (Infrastructure):** VPC, Load Balancing, Launch Templates.
- **Student 2 (Application Layer):** Python Portal architecture, API mapping, Jinja2 design.
- **Student 3 (Backend/Sec):** Single-AZ Database paradigms, HTTPS enablement, KMS integrations.
- **Student 4 (Observability):** Serverless event queue models, AWS Telemetry, Deploy Runbooks.
