# GymAxis AI - Supplier Integration Guide

## Quick Start for Suppliers

Welcome to GymAxis AI's Supplier Integration System! This guide will help you integrate your systems with GymAxis AI to:
- Automatically sync equipment data
- Receive real-time issue notifications
- Manage service requests
- Update equipment status and warranty information

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Authentication](#authentication)
3. [API Endpoints](#api-endpoints)
4. [Webhooks](#webhooks)
5. [Use Cases](#use-cases)
6. [Code Examples](#code-examples)
7. [Support](#support)

---

## Getting Started

### Step 1: Get Your API Key

1. Log into your GymAxis AI customer dashboard at: https://your-domain.com/dashboard
2. Navigate to **Settings** → **API Keys**
3. Click **"Generate New API Key"**
4. **IMPORTANT**: Copy and store your API key securely. It will look like: `gfx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### Step 2: Test Your Connection

```bash
curl -X GET "https://your-domain.com/api/v1/supplier/health" \
  -H "X-API-Key: YOUR_API_KEY"
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

---

## Authentication

All API requests require authentication using an API key sent in the `X-API-Key` header.

```bash
X-API-Key: gfx_your_api_key_here
```

---

## API Endpoints

### Base URL
```
https://your-domain.com/api/v1/supplier
```

### Equipment Management

#### 1. List All Equipment
Get all equipment installed at customer site.

```bash
GET /equipment
```

**Response:**
```json
{
  "equipment": [
    {
      "id": "uuid",
      "name": "Treadmill 1",
      "equipment_type": "Treadmill",
      "manufacturer": "Life Fitness",
      "model": "T5-Go",
      "serial_number": "SN123456",
      "purchase_date": "2024-01-15",
      "warranty_expiry": "2027-01-15",
      "stats": {
        "total_issues": 3,
        "open_issues": 1,
        "days_in_service": 450
      }
    }
  ],
  "count": 1
}
```

#### 2. Get Equipment Details
Get detailed information about specific equipment.

```bash
GET /equipment/{equipment_id}
```

#### 3. Create Equipment
Add new equipment when installing at customer site.

```bash
POST /equipment
Content-Type: application/json

{
  "name": "Treadmill 2",
  "equipment_type": "Treadmill",
  "manufacturer": "Life Fitness",
  "model": "T5-Go",
  "serial_number": "SN789012",
  "purchase_date": "2026-04-01",
  "warranty_expiry": "2029-04-01",
  "length": 2.5,
  "width": 1.5,
  "height": 1.8,
  "notes": "New installation"
}
```

#### 4. Update Equipment
Update equipment details (e.g., after maintenance or part replacement).

```bash
PATCH /equipment/{equipment_id}
Content-Type: application/json

{
  "notes": "Belt replaced on 2026-04-03",
  "warranty_expiry": "2028-04-03"
}
```

### Issue Management

#### 5. List Issues
View all reported issues, optionally filtered.

```bash
GET /issues?status=open&severity=critical
```

Query parameters:
- `status`: open | in_progress | resolved
- `severity`: low | medium | critical

#### 6. Report Issue
Create new issue (useful when you identify problems during maintenance visits).

```bash
POST /issues
Content-Type: application/json

{
  "machine_name": "Treadmill 1",
  "machine_type": "Treadmill",
  "issue_description": "Belt requires replacement - showing significant wear",
  "severity": "medium"
}
```

#### 7. Update Issue Status
Mark issue as resolved after fixing.

```bash
PATCH /issues/{issue_id}?status=resolved
```

### Service Requests

#### 8. List Service Requests
View all service callout requests from customers.

```bash
GET /service-requests
```

**Response:**
```json
{
  "service_requests": [
    {
      "id": "uuid",
      "machine_type": "Treadmill",
      "issue_summary": "Motor fault - unusual noise",
      "site_info": "Main Gym Floor, London",
      "contact_name": "John Smith",
      "contact_email": "john@gym.com",
      "contact_phone": "+44 20 1234 5678",
      "status": "pending",
      "created_at": "2026-04-03T10:00:00Z"
    }
  ],
  "count": 1
}
```

#### 9. Update Service Request
Update status after completing service.

```bash
PATCH /service-requests/{request_id}?status=completed
```

Statuses: `pending` | `in_progress` | `completed` | `cancelled`

---

## Webhooks

### Real-Time Notifications

Instead of polling the API, register a webhook URL to receive instant notifications when events occur.

### Register Webhook

```bash
POST /webhooks/register
Content-Type: application/json

{
  "url": "https://your-system.com/webhooks/gymaxis",
  "events": [
    "issue.created",
    "service_request.created",
    "equipment.updated"
  ]
}
```

### Available Events

- `issue.created` - New issue reported
- `issue.updated` - Issue status changed
- `service_request.created` - Customer requested service callout
- `service_request.updated` - Service request status changed
- `equipment.created` - New equipment added
- `equipment.updated` - Equipment details modified

### Webhook Payload Example

```json
{
  "event": "service_request.created",
  "timestamp": "2026-04-03T10:00:00Z",
  "data": {
    "id": "uuid",
    "machine_type": "Treadmill",
    "issue_summary": "Motor fault",
    "site_info": "Main Gym, London",
    "contact_name": "John Smith",
    "contact_email": "john@gym.com",
    "contact_phone": "+44 20 1234 5678",
    "status": "pending"
  }
}
```

### Webhook Security

Verify webhook authenticity by checking the `X-GymAxis-Signature` header (coming soon).

---

## Use Cases

### Use Case 1: New Equipment Installation

When you install new equipment at a customer site:

```python
import requests

API_KEY = "gfx_your_api_key"
BASE_URL = "https://your-domain.com/api/v1/supplier"

equipment_data = {
    "name": "Treadmill 5",
    "equipment_type": "Treadmill",
    "manufacturer": "Life Fitness",
    "model": "T5-Go",
    "serial_number": "SN987654",
    "purchase_date": "2026-04-03",
    "warranty_expiry": "2029-04-03",
    "notes": "Installed during gym expansion"
}

response = requests.post(
    f"{BASE_URL}/equipment",
    json=equipment_data,
    headers={"X-API-Key": API_KEY}
)

print(response.json())
```

### Use Case 2: Proactive Maintenance

Automatically check for equipment needing attention:

```python
import requests

API_KEY = "gfx_your_api_key"
BASE_URL = "https://your-domain.com/api/v1/supplier"

# Get all equipment
response = requests.get(
    f"{BASE_URL}/equipment",
    headers={"X-API-Key": API_KEY}
)

equipment_list = response.json()["equipment"]

# Find equipment with open issues
needs_attention = [
    eq for eq in equipment_list 
    if eq["stats"]["open_issues"] > 0
]

print(f"Equipment needing attention: {len(needs_attention)}")
for eq in needs_attention:
    print(f"- {eq['name']}: {eq['stats']['open_issues']} open issues")
```

### Use Case 3: Service Request Management

Automatically sync service requests to your dispatch system:

```javascript
const axios = require('axios');

const API_KEY = 'gfx_your_api_key';
const BASE_URL = 'https://your-domain.com/api/v1/supplier';

async function syncServiceRequests() {
  const response = await axios.get(`${BASE_URL}/service-requests`, {
    headers: { 'X-API-Key': API_KEY }
  });
  
  const pendingRequests = response.data.service_requests.filter(
    sr => sr.status === 'pending'
  );
  
  // Add to your dispatch system
  for (const request of pendingRequests) {
    console.log(`New service request: ${request.issue_summary}`);
    console.log(`Contact: ${request.contact_name} - ${request.contact_phone}`);
    
    // Your dispatch logic here
    // ...
    
    // Update status
    await axios.patch(
      `${BASE_URL}/service-requests/${request.id}?status=in_progress`,
      {},
      { headers: { 'X-API-Key': API_KEY } }
    );
  }
}

syncServiceRequests();
```

### Use Case 4: Webhook Handler (Node.js/Express)

```javascript
const express = require('express');
const app = express();

app.use(express.json());

app.post('/webhooks/gymaxis', (req, res) => {
  const { event, data, timestamp } = req.body;
  
  console.log(`Received webhook: ${event} at ${timestamp}`);
  
  switch(event) {
    case 'service_request.created':
      // Trigger dispatch system
      console.log(`New service request: ${data.issue_summary}`);
      // Your logic here
      break;
      
    case 'issue.created':
      // Log issue in your system
      console.log(`New issue reported: ${data.issue_description}`);
      // Your logic here
      break;
  }
  
  res.json({ received: true });
});

app.listen(3000, () => {
  console.log('Webhook server listening on port 3000');
});
```

---

## Code Examples by Language

### Python

```python
import requests

class GymAxisAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://your-domain.com/api/v1/supplier"
        self.headers = {"X-API-Key": api_key}
    
    def get_equipment(self):
        response = requests.get(
            f"{self.base_url}/equipment",
            headers=self.headers
        )
        return response.json()
    
    def create_issue(self, machine_name, machine_type, description, severity="medium"):
        data = {
            "machine_name": machine_name,
            "machine_type": machine_type,
            "issue_description": description,
            "severity": severity
        }
        response = requests.post(
            f"{self.base_url}/issues",
            json=data,
            headers=self.headers
        )
        return response.json()

# Usage
api = GymAxisAPI("gfx_your_api_key")
equipment = api.get_equipment()
print(f"Total equipment: {equipment['count']}")
```

### JavaScript/Node.js

```javascript
const axios = require('axios');

class GymAxisAPI {
  constructor(apiKey) {
    this.apiKey = apiKey;
    this.baseURL = 'https://your-domain.com/api/v1/supplier';
    this.headers = { 'X-API-Key': apiKey };
  }
  
  async getEquipment() {
    const response = await axios.get(`${this.baseURL}/equipment`, {
      headers: this.headers
    });
    return response.data;
  }
  
  async updateEquipment(equipmentId, updates) {
    const response = await axios.patch(
      `${this.baseURL}/equipment/${equipmentId}`,
      updates,
      { headers: this.headers }
    );
    return response.data;
  }
}

// Usage
const api = new GymAxisAPI('gfx_your_api_key');
const equipment = await api.getEquipment();
console.log(`Total equipment: ${equipment.count}`);
```

### PHP

```php
<?php

class GymAxisAPI {
    private $apiKey;
    private $baseURL = 'https://your-domain.com/api/v1/supplier';
    
    public function __construct($apiKey) {
        $this->apiKey = $apiKey;
    }
    
    public function getEquipment() {
        $ch = curl_init($this->baseURL . '/equipment');
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'X-API-Key: ' . $this->apiKey
        ]);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        $response = curl_exec($ch);
        curl_close($ch);
        return json_decode($response, true);
    }
}

// Usage
$api = new GymAxisAPI('gfx_your_api_key');
$equipment = $api->getEquipment();
echo "Total equipment: " . $equipment['count'];
?>
```

---

## Best Practices

1. **Secure API Keys**
   - Never commit API keys to version control
   - Store in environment variables
   - Rotate keys regularly

2. **Error Handling**
   - Always check HTTP status codes
   - Implement retry logic with exponential backoff
   - Log all API interactions for debugging

3. **Rate Limiting**
   - Current limit: 1000 requests/hour per API key
   - Implement caching where possible
   - Use webhooks instead of polling

4. **Webhooks vs Polling**
   - Use webhooks for real-time updates
   - Only poll when webhooks aren't feasible
   - If polling, use reasonable intervals (e.g., every 5-10 minutes)

5. **Data Validation**
   - Validate all input before sending to API
   - Handle API validation errors gracefully
   - Keep local data in sync with API responses

---

## Error Handling

### HTTP Status Codes

- `200` - Success
- `201` - Created
- `400` - Bad Request (validation error)
- `401` - Unauthorized (invalid API key)
- `404` - Not Found
- `429` - Rate Limit Exceeded
- `500` - Internal Server Error

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Testing

### Sandbox Environment

Use test API keys (prefix: `gfx_test_`) for development and testing. Test keys have the same capabilities but don't affect production data.

### Testing Checklist

- [ ] Successful authentication
- [ ] Create equipment
- [ ] List equipment
- [ ] Update equipment
- [ ] Create issue
- [ ] List issues
- [ ] Register webhook
- [ ] Handle webhook events

---

## Support

### API Support
- **Email**: api@gymaxisai.com
- **Documentation**: https://your-domain.com/api-docs
- **Status Page**: https://status.gymaxisai.com (coming soon)

### Integration Assistance
Our team can help you integrate:
- Custom webhook implementations
- Bulk data imports
- Custom reporting
- SSO integration

Contact us at: integrations@gymaxisai.com

---

## Changelog

### Version 1.0.0 (April 2026)
- Initial API release
- Equipment management endpoints
- Issue tracking endpoints
- Service request management
- Webhook support

---

## Frequently Asked Questions

**Q: How do I test without affecting production data?**
A: Use test API keys (prefix: `gfx_test_`) which work identically but in a sandboxed environment.

**Q: Can I have multiple API keys?**
A: Yes! Generate separate keys for different integrations or environments.

**Q: What happens if my API key is compromised?**
A: Immediately revoke the key in your dashboard and generate a new one. Previous keys are invalidated instantly.

**Q: Do webhooks guarantee delivery?**
A: We retry failed webhooks up to 3 times with exponential backoff. Implement idempotency in your handlers.

**Q: Can I filter equipment by location/site?**
A: Yes, use query parameters like `?site=London` when calling `/equipment`.

**Q: Is there a test environment?**
A: Yes, use API keys with `gfx_test_` prefix to access the test environment.

---

© 2026 GymAxis AI. All rights reserved.
