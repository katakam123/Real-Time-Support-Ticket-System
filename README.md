# Real-Time Support Ticket System

## 1. Project Overview

The Real-Time Support Ticket System is a backend application built with FastAPI to manage customer support tickets, agent assignments, SLA monitoring, real-time chat, notifications, and customer feedback.

### Features

- JWT authentication and role-based access control.
- Admin, Agent, and Customer roles.
- Ticket creation, assignment, status updates, and reopening.
- Ticket categories and priorities.
- Automatic SLA monitoring and breach notifications.
- Real-time ticket chat using WebSockets.
- Real-time agent notifications.
- Internal notes for authorized support staff.
- Customer feedback and ratings.
- Pagination, filtering, and sorting.
- Dashboard and reporting APIs.
- Chat attachments for supported images and PDF files up to 5 MB.
- Email notifications for ticket creation, resolution, and SLA breaches.
- MySQL database with Alembic migrations.

## 2. Technology Stack

- Python 3.9+
- FastAPI
- Pydantic
- SQLAlchemy Async
- MySQL
- aiomysql
- Alembic
- JWT authentication
- Passlib/bcrypt
- WebSockets
- APScheduler
- FastAPI BackgroundTasks
- SMTP email

## 3. Project Structure

```text
support_ticket_system/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models/
│   │   └── entities.py
│   ├── schemas/
│   ├── routers/
│   ├── services/
│   ├── auth/
│   ├── websockets/
│   └── jobs/
├── alembic/
│   └── versions/
├── uploads/
├── tests/
├── alembic.ini
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

The structure above is illustrative. Update it to match the files actually present in the repository.

## 4. Prerequisites

Install the following:

- Python 3.9 or later, using a version compatible with the installed dependencies.
- MySQL Server.
- Git.
- Visual Studio Code.

## 5. Installation and Setup

### Step 1: Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd support_ticket_system
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with the actual repository URL.

### Step 2: Create a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Step 4: Create the MySQL database

Create a database in MySQL:

```sql
CREATE DATABASE support_ticket_db;
```

Use the database name configured in your application if it differs.

### Step 5: Configure environment variables

Create a `.env` file in the project root using the variables expected by your application.

Example configuration:

```env
DATABASE_URL=mysql+aiomysql://DB_USER:DB_PASSWORD@localhost:3306/support_ticket_db
SECRET_KEY=REPLACE_WITH_A_RANDOM_SECRET
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
```

Adjust variable names to match your settings and database configuration. URL-encode special characters in the database password when necessary.

**Security:** Never commit `.env`, database passwords, JWT secrets, or SMTP credentials.

### Step 6: Run database migrations

Check that Alembic is configured correctly and that the database is reachable.

View migration history:

```powershell
alembic history
```

Check the current database revision:

```powershell
alembic current
```

Apply migrations:

```powershell
alembic upgrade head
```

Create a migration after model changes:

```powershell
alembic revision --autogenerate -m "describe the schema change"
```

Review the generated migration before applying it.

To inspect the SQL that would be generated:

```powershell
alembic upgrade head --sql
```

Commit all required migration files in `alembic/versions/`. Do not delete existing migrations to make the project appear clean.

### Step 7: Start the application

```powershell
uvicorn app.main:app --reload
```

Application URL:

http://127.0.0.1:8000

Swagger API documentation:

http://127.0.0.1:8000/docs

ReDoc documentation:

http://127.0.0.1:8000/redoc

## 6. User Roles and Test Credentials

The application supports the following roles:

| Role | Responsibilities |
|---|---|
| Admin | Manage agents, categories, ticket assignments, reports, and system operations. |
| Agent | Handle assigned tickets, communicate with customers, and update ticket statuses. |
| Customer | Create tickets, view their own tickets, chat with support, and submit feedback. |

### Local test accounts

Populate this table with accounts actually created and tested in your local environment.

| Role | Email | Password |
|---|---|---|
| Admin | YOUR_ADMIN_TEST_EMAIL | YOUR_ADMIN_TEST_PASSWORD |
| Agent | YOUR_AGENT_TEST_EMAIL | YOUR_AGENT_TEST_PASSWORD |
| Customer | YOUR_CUSTOMER_TEST_EMAIL | YOUR_CUSTOMER_TEST_PASSWORD |

These are placeholders, not working credentials.

Use your project's approved account-creation process. If public registration only creates Customers, create Admin and Agent accounts through the appropriate administrative or development setup process.

Do not publish real personal accounts or production passwords in this README. Prefer disposable local test accounts.

## 7. Authentication

1. Open Swagger UI.
2. Register a Customer or use an existing test account.
3. Sign in through the configured login endpoint.
4. Copy the access token from the response.
5. Click **Authorize** in Swagger.
6. Enter the token in the format required by the configured authentication scheme.
7. Execute protected endpoints using the authorized session.

Access tokens expire according to the configured expiry time. Follow the application's refresh-token workflow if implemented.

## 8. WebSocket Testing

Use two separate authenticated browser sessions or a WebSocket client.

### Ticket chat

The WebSocket endpoint follows this pattern if implemented by the application:

```text
ws://127.0.0.1:8000/ws/tickets/{ticket_id}?token={ACCESS_TOKEN}
```

Replace `{ticket_id}` and `{ACCESS_TOKEN}` with actual values.

Testing procedure:

1. Sign in as a Customer and create a ticket.
2. Sign in as an authorized Agent.
3. Assign the ticket to the Agent if assignment is required.
4. Obtain the ticket ID and both users' access tokens.
5. Connect both clients to the ticket WebSocket.
6. Send a message from the Customer.
7. Verify that the Agent receives the message.
8. Send a reply from the Agent.
9. Verify that the Customer receives the reply.
10. Test authorization failures and the restrictions on closed tickets and internal notes.

### Notification WebSocket

If implemented, the notification endpoint follows this pattern:

```text
ws://127.0.0.1:8000/ws/notifications?token={ACCESS_TOKEN}
```

Verify that the authenticated user receives the notifications permitted by their role.

The WebSocket routes and message formats documented here must match the actual implementation.

## 9. Ticket Workflow

The ticket workflow may include these states, depending on the configured transition rules:

- Open
- Assigned
- In Progress
- Waiting on Customer
- Resolved
- Closed

Test valid transitions, unauthorized transitions, ticket ownership, reassignment, and reopening restrictions.

## 10. SLA Policies

Document the actual policies configured in the application.

Example policy values:

| Priority | First Response Target | Resolution Target |
|---|---:|---:|
| Low | 24 hours | 72 hours |
| Medium | 8 hours | 48 hours |
| High | 2 hours | 24 hours |
| Urgent | 30 minutes | 8 hours |

Confirm that these values match the seeded database policies and that scheduled jobs are enabled.

## 11. File Attachments and Email

### File attachments

Supported file types, if enabled:

- JPEG
- PNG
- GIF
- PDF

Maximum upload size: 5 MB.

Verify file-size validation, type validation, ticket-level authorization, and authenticated downloads. Uploaded files should not be exposed through unrestricted public URLs.

### Email notifications

Configure SMTP environment variables before testing.

Verify that emails are triggered for:

- Ticket creation.
- Ticket resolution.
- SLA breaches.

SMTP delivery depends on the configured provider and credentials. Background task failures should be logged and handled appropriately.

## 12. Reports and Dashboard

Document the endpoints implemented by your application, such as:

- `GET /reports/dashboard`
- `GET /reports/agent-performance`
- `GET /reports/category-summary`
- `GET /reports/sla-summary`
- `GET /reports/customer-satisfaction`

These endpoints should be restricted to authorized administrators if that is the configured access policy.

## 13. Testing

Start the application and open Swagger UI.

Test at least:

- Successful login and invalid credentials.
- Role-based access restrictions.
- Ticket creation and validation.
- Ticket assignment and status transitions.
- Filtering, sorting, and pagination.
- WebSocket communication.
- Attachment size and type restrictions.
- SLA breach detection.
- Email notifications.
- Report calculations.

If automated tests exist, run them with:

```powershell
python -m pytest
```

## 14. Screenshots

Store genuine screenshots in a directory such as:

```text
docs/
└── screenshots/
    ├── swagger-authentication.png
    ├── swagger-ticket-creation.png
    ├── swagger-ticket-list.png
    ├── swagger-ticket-status.png
    ├── customer-chat.png
    ├── agent-chat.png
    └── reports-dashboard.png
```

Capture the successful responses from your own application. Include the Customer and Agent views of the same conversation. Do not include access tokens, passwords, private customer information, or SMTP secrets.

Only list screenshots that have actually been captured and committed.

## 15. Assumptions and Limitations

Document the following according to the actual implementation:

- The Customer role is assigned through public registration.
- Privileged accounts are created through an authorized process.
- Ticket access is limited according to role and ownership or assignment rules.
- SLA targets are configured per priority.
- The application uses MySQL for persistence.
- Alembic manages database schema changes.
- WebSocket clients must authenticate and be authorized for the relevant ticket.
- Email delivery depends on external SMTP availability.
- Attachment access is restricted to authorized users.
- The configured timezone, SLA calendar, and handling of weekends or holidays must be specified.
- Any features that are planned but not implemented must be identified clearly.

## 16. GitHub Submission

Before submitting:

```powershell
git status
git add README.md requirements.txt app alembic
git commit -m "Complete support ticket system documentation"
git push
```

Add the screenshots and other required project files using Git as well.

Check `.gitignore` before staging files. Exclude `.venv/`, `.env`, cache directories, logs, and private uploaded files.

## 17. Conclusion

This project demonstrates REST API development, authentication, role-based authorization, asynchronous database access, schema migrations, real-time communication, SLA monitoring, reporting, file handling, and email integration using FastAPI.
