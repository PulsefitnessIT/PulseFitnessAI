#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: >
  White-label conversion of the GymAxis AI platform into Pulse Fitness AI. Every user-facing
  surface must show Pulse Fitness AI (no GymAxis branding, URLs, emails, titles or logos).
  Database reset to a clean state keeping only the Master Admin. Integration key rotation
  deferred to a later phase (user will provide new Pulse keys). Domain: https://www.pulsefitness.ai.

backend:
  - task: "Master Admin auth after DB reset + email rename to admin@pulsefitness.com"
    implemented: true
    working: true
    file: "backend/bootstrap/seed.py, backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Database cleared via scripts/reset_to_pulse.py (kept global reference data only). Backend restarted; seed re-created the master admin from env. Login is admin@pulsefitness.com / MasterAdmin123!. SEED_TEST_ACCOUNTS=0 so no fixture users. Verify login (POST /api/auth/login) returns a token and master-admin access works."
        - working: true
          agent: "testing"
          comment: "✅ PASSED - Master admin login successful with admin@pulsefitness.com / MasterAdmin123!. POST /api/auth/login returned 200 with valid token. User ID: 1fedcc01-1f53-408a-bc48-017375348536, is_master_admin: true. Database seed working correctly after reset."
  - task: "Backend health + core API still functional after global GymAxis->Pulse text rebrand (2193 substitutions across .py)"
    implemented: true
    working: true
    file: "backend/ (many files)"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "A scripted case-sensitive rebrand replaced GymAxis display strings + gymaxisai.com domains/emails across backend (excluding tests). No Python syntax errors on reload and /api/health=200. Verify representative endpoints (auth, /api/me or equivalent, a CRM/memberships read) still respond without 500s introduced by the string changes."
        - working: true
          agent: "testing"
          comment: "✅ PASSED - All smoke tests passed (6/6, 100% success rate). GET /api/health returned 200. Authenticated endpoints tested: GET /api/auth/me (200), GET /api/master-admin/organizations (200, 3 orgs), GET /api/organization (200, org name: 'Pulse Fitness AI Admin'), GET /api/memberships/members (200, 0 members). No 500 errors detected. Text rebrand did not break JSON serialization or route logic."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus:
    - "Master Admin auth after DB reset + email rename to admin@pulsefitness.com"
    - "Backend health + core API still functional after global GymAxis->Pulse text rebrand (2193 substitutions across .py)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: >
        Phase 1+ of the Pulse Fitness white-label is done. Please run BACKEND-ONLY smoke tests:
        (1) Master Admin login with admin@pulsefitness.com / MasterAdmin123! (POST /api/auth/login)
        returns a valid token; (2) backend /api/health = 200; (3) 2-3 representative authenticated
        reads (e.g. master-admin or CRM/memberships list endpoints) return 2xx (not 500) to confirm
        the global text rebrand didn't break serialization/logic. Do NOT test integrations that need
        external keys (Stripe live / email sending) — key rotation is a later phase. Credentials are
        in /app/memory/test_credentials.md.
    - agent: "testing"
      message: >
        ✅ Backend smoke test COMPLETE - All tests PASSED (6/6, 100% success rate). 
        
        Results:
        1. ✅ GET /api/health → 200 OK
        2. ✅ POST /api/auth/login (admin@pulsefitness.com) → 200 with valid token, is_master_admin=true
        3. ✅ GET /api/auth/me → 200 (authenticated read)
        4. ✅ GET /api/master-admin/organizations → 200 (3 organizations found)
        5. ✅ GET /api/organization → 200 (org name: "Pulse Fitness AI Admin")
        6. ✅ GET /api/memberships/members → 200 (0 members, clean DB)
        
        No 500 errors detected. The white-label rebrand (GymAxis → Pulse Fitness, 2193 substitutions)
        did NOT break JSON serialization or route logic. Master admin authentication working correctly
        after database reset. Backend is healthy and ready for use.
