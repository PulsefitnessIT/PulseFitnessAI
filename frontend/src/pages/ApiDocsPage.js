import React from 'react';
import Navbar from '../components/shared/Navbar';
import Footer from '../components/shared/Footer';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const ApiDocsPage = () => {
  const baseUrl = process.env.REACT_APP_BACKEND_URL || 'https://your-domain.com';

  return (
    <div className="min-h-screen bg-[var(--color-ink-alt)]">
      <Navbar />
      
      <div className="pt-32 pb-20 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="mb-12">
            <span className="text-xs tracking-[0.2em] uppercase font-bold text-[var(--color-brand-blue)]">DEVELOPER API</span>
            <h1 className="text-5xl font-bold text-white mt-4 mb-6" data-testid="api-docs-title">
              Supplier Integration API
            </h1>
            <p className="text-lg text-[var(--color-text-muted)]">
              Connect your supplier systems directly to GymAxis AI for seamless equipment management, issue tracking, and service coordination.
            </p>
          </div>

          {/* Getting Started */}
          <Card className="bg-[var(--theme-surface)] border-white/10 p-8 mb-8">
            <h2 className="text-3xl font-semibold text-white mb-4">Getting Started</h2>
            
            <div className="space-y-6">
              <div>
                <h3 className="text-xl font-semibold text-white mb-3">1. Generate API Key</h3>
                <p className="text-[var(--color-text-muted)] mb-3">
                  Log into your GymAxis AI dashboard and navigate to Settings \u2192 API Keys. Click "Generate New API Key" and store it securely.
                </p>
                <div className="bg-[var(--color-ink-alt)] border border-white/10 rounded-lg p-4 font-mono text-sm text-[var(--color-brand-blue)]">
                  API Key Format: gfx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
                </div>
              </div>

              <div>
                <h3 className="text-xl font-semibold text-white mb-3">2. Authentication</h3>
                <p className="text-[var(--color-text-muted)] mb-3">
                  Include your API key in the X-API-Key header with every request:
                </p>
                <div className="bg-[var(--color-ink-alt)] border border-white/10 rounded-lg p-4 overflow-x-auto">
                  <pre className="text-sm text-white">
{`curl -X GET "${baseUrl}/api/v1/supplier/equipment" \\
  -H "X-API-Key: gfx_your_api_key_here"`}
                  </pre>
                </div>
              </div>

              <div>
                <h3 className="text-xl font-semibold text-white mb-3">3. Base URL</h3>
                <div className="bg-[var(--color-ink-alt)] border border-white/10 rounded-lg p-4 font-mono text-sm text-[var(--color-brand-blue)]">
                  {baseUrl}/api/v1/supplier
                </div>
              </div>
            </div>
          </Card>

          {/* API Endpoints */}
          <Tabs defaultValue="equipment" className="w-full">
            <TabsList className="bg-[var(--theme-surface)] border border-white/10 mb-6">
              <TabsTrigger value="equipment">Equipment</TabsTrigger>
              <TabsTrigger value="issues">Issues</TabsTrigger>
              <TabsTrigger value="service">Service Requests</TabsTrigger>
              <TabsTrigger value="webhooks">Webhooks</TabsTrigger>
            </TabsList>

            {/* Equipment Endpoints */}
            <TabsContent value="equipment" className="space-y-6">
              <EndpointCard
                method="GET"
                endpoint="/equipment"
                title="List All Equipment"
                description="Retrieve all equipment for the authenticated customer"
                response={`{
  "equipment": [
    {
      "id": "uuid",
      "name": "Treadmill 1",
      "equipment_type": "Treadmill",
      "manufacturer": "Life Fitness",
      "model": "T5-Go",
      "serial_number": "SN123456",
      "stats": {
        "total_issues": 3,
        "open_issues": 1,
        "total_audits": 2
      }
    }
  ],
  "count": 1
}`}
              />

              <EndpointCard
                method="GET"
                endpoint="/equipment/{equipment_id}"
                title="Get Equipment Details"
                description="Get detailed information about specific equipment including issue history"
                response={`{
  "id": "uuid",
  "name": "Treadmill 1",
  "equipment_type": "Treadmill",
  "manufacturer": "Life Fitness",
  "stats": {...},
  "issues": [...]
}`}
              />

              <EndpointCard
                method="POST"
                endpoint="/equipment"
                title="Create Equipment"
                description="Add new equipment to customer site (useful when installing new machines)"
                requestBody={`{
  "name": "Treadmill 2",
  "equipment_type": "Treadmill",
  "manufacturer": "Life Fitness",
  "model": "T5-Go",
  "serial_number": "SN789012",
  "warranty_expiry": "2027-12-31"
}`}
              />

              <EndpointCard
                method="PATCH"
                endpoint="/equipment/{equipment_id}"
                title="Update Equipment"
                description="Update equipment details"
                requestBody={`{
  "notes": "Belt replaced on 2026-04-03",
  "warranty_expiry": "2028-04-03"
}`}
              />
            </TabsContent>

            {/* Issues Endpoints */}
            <TabsContent value="issues" className="space-y-6">
              <EndpointCard
                method="GET"
                endpoint="/issues?status=open&severity=critical"
                title="List Issues"
                description="List all issues with optional filtering by status and severity"
                response={`{
  "issues": [
    {
      "id": "uuid",
      "machine_name": "Treadmill 1",
      "machine_type": "Treadmill",
      "issue_description": "Belt slipping",
      "severity": "critical",
      "status": "open",
      "created_at": "2026-04-03T10:00:00Z"
    }
  ],
  "count": 1
}`}
              />

              <EndpointCard
                method="POST"
                endpoint="/issues"
                title="Create Issue"
                description="Report equipment problems (useful for suppliers identifying issues during maintenance)"
                requestBody={`{
  "machine_name": "Treadmill 1",
  "machine_type": "Treadmill",
  "issue_description": "Belt requires replacement",
  "severity": "medium"
}`}
              />

              <EndpointCard
                method="PATCH"
                endpoint="/issues/{issue_id}?status=resolved"
                title="Update Issue Status"
                description="Update issue status after resolution"
              />
            </TabsContent>

            {/* Service Requests */}
            <TabsContent value="service" className="space-y-6">
              <EndpointCard
                method="GET"
                endpoint="/service-requests"
                title="List Service Requests"
                description="View all service callout requests from customers"
                response={`{
  "service_requests": [
    {
      "id": "uuid",
      "machine_type": "Treadmill",
      "issue_summary": "Motor fault",
      "site_info": "Main Gym, London",
      "contact_name": "John Smith",
      "contact_email": "john@gym.com",
      "status": "pending",
      "created_at": "2026-04-03T10:00:00Z"
    }
  ],
  "count": 1
}`}
              />

              <EndpointCard
                method="PATCH"
                endpoint="/service-requests/{request_id}?status=completed"
                title="Update Service Request"
                description="Update status after completing service callout"
              />
            </TabsContent>

            {/* Webhooks */}
            <TabsContent value="webhooks" className="space-y-6">
              <Card className="bg-[var(--theme-surface)] border-white/10 p-6">
                <h3 className="text-xl font-semibold text-white mb-3">Real-Time Notifications</h3>
                <p className="text-[var(--color-text-muted)] mb-4">
                  Register a webhook URL to receive real-time notifications when events occur (new issues, service requests, equipment updates).
                </p>
              </Card>

              <EndpointCard
                method="POST"
                endpoint="/webhooks/register"
                title="Register Webhook"
                description="Set up webhook endpoint for real-time notifications"
                requestBody={`{
  "url": "https://your-system.com/webhooks/gymaxis",
  "events": [
    "issue.created",
    "service_request.created",
    "equipment.updated"
  ]
}`}
              />

              <Card className="bg-[var(--color-ink-alt)] border border-white/10 p-6">
                <h4 className="text-lg font-semibold text-white mb-3">Webhook Payload Example</h4>
                <pre className="text-sm text-[var(--color-text-muted)] overflow-x-auto">
{`{
  "event": "issue.created",
  "timestamp": "2026-04-03T10:00:00Z",
  "data": {
    "id": "uuid",
    "machine_name": "Treadmill 1",
    "issue_description": "Belt slipping",
    "severity": "critical"
  }
}`}
                </pre>
              </Card>
            </TabsContent>
          </Tabs>

          {/* Rate Limits & Best Practices */}
          <Card className="bg-[var(--theme-surface)] border-white/10 p-8 mt-8">
            <h2 className="text-2xl font-semibold text-white mb-4">Best Practices</h2>
            <ul className="space-y-3 text-[var(--color-text-muted)]">
              <li className="flex items-start">
                <span className="text-[var(--color-brand-blue)] mr-3">\u2022</span>
                <span><strong className="text-white">Store API keys securely</strong> - Never commit keys to version control</span>
              </li>
              <li className="flex items-start">
                <span className="text-[var(--color-brand-blue)] mr-3">\u2022</span>
                <span><strong className="text-white">Use webhooks</strong> for real-time updates instead of polling</span>
              </li>
              <li className="flex items-start">
                <span className="text-[var(--color-brand-blue)] mr-3">\u2022</span>
                <span><strong className="text-white">Handle errors gracefully</strong> - Check HTTP status codes and error messages</span>
              </li>
              <li className="flex items-start">
                <span className="text-[var(--color-brand-blue)] mr-3">\u2022</span>
                <span><strong className="text-white">Rate limit</strong>: 1000 requests per hour per API key</span>
              </li>
            </ul>
          </Card>

          {/* Support */}
          <Card className="bg-gradient-to-br from-[rgb(var(--rgb-brand-blue)/0.2)] to-[rgb(var(--rgb-brand-blue)/0.05)] border border-[rgb(var(--rgb-brand-blue)/0.3)] p-8 mt-8 text-center">
            <h2 className="text-2xl font-semibold text-white mb-2">Need Help?</h2>
            <p className="text-[var(--color-text-muted)] mb-4">
              Our integration team is here to help you get connected
            </p>
            <p className="text-white">
              Email: <a href="mailto:api@gymaxisai.com" className="text-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue-alt)]">api@gymaxisai.com</a>
            </p>
          </Card>
        </div>
      </div>

      <Footer />
    </div>
  );
};

const EndpointCard = ({ method, endpoint, title, description, requestBody, response }) => {
  const methodColors = {
    GET: 'bg-green-500/20 text-green-400',
    POST: 'bg-blue-500/20 text-blue-400',
    PATCH: 'bg-yellow-500/20 text-yellow-400',
    DELETE: 'bg-red-500/20 text-red-400'
  };

  return (
    <Card className="bg-[var(--theme-surface)] border-white/10 p-6">
      <div className="flex items-center space-x-3 mb-3">
        <Badge className={methodColors[method]}>{method}</Badge>
        <code className="text-[var(--color-brand-blue)] font-mono">{endpoint}</code>
      </div>
      <h3 className="text-xl font-semibold text-white mb-2">{title}</h3>
      <p className="text-[var(--color-text-muted)] mb-4">{description}</p>
      
      {requestBody && (
        <div className="mb-4">
          <p className="text-white text-sm font-semibold mb-2">Request Body:</p>
          <div className="bg-[var(--color-ink-alt)] border border-white/10 rounded-lg p-4 overflow-x-auto">
            <pre className="text-sm text-[var(--color-text-muted)]">{requestBody}</pre>
          </div>
        </div>
      )}
      
      {response && (
        <div>
          <p className="text-white text-sm font-semibold mb-2">Response:</p>
          <div className="bg-[var(--color-ink-alt)] border border-white/10 rounded-lg p-4 overflow-x-auto">
            <pre className="text-sm text-[var(--color-text-muted)]">{response}</pre>
          </div>
        </div>
      )}
    </Card>
  );
};

export default ApiDocsPage;
