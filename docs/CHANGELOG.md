# Changelog

All notable changes to Workflow Hub since the core architecture refactor.

## [0.1.0] - 2026-01-04

### Core Features

**Director Resilience and Workflow MCP Integration**
- Added Director resilience for handling pipeline failures
- Integrated with Workflow MCP (Model Context Protocol) for enhanced agent communication
- Improved workflow handling and task management

**Proof-of-Work System**
- Added capability to show proof-of-work screenshots as thumbnails on kanban cards
- Implemented screenshot analysis for QA agents
- Enhanced UI validation in automated tests

**Job Queue System Improvements**
- Enhanced Job Queue Status UI to show agent type and task details
- Improved task display with task_ref and title instead of numeric IDs
- Added proper job status tracking and visualization

### Bug Fixes

**Kanban Board Enhancements**
- Fixed issues with board blank cards and tasks URL redirect
- Made kanban cards more compact and show DONE tasks
- Improved board column height and scrolling behavior
- Added project filter to global task board

**LLM Service Improvements**
- Fixed context size configuration for Docker Model Runner
- Added context size recovery mechanism after errors
- Improved model configuration and error handling

### API and Infrastructure

**Settings Page**
- Added inline editing with immediate save capability
- Implemented Director status card with start/stop toggle
- Added category grouping with icons
- Integrated toast notifications for user feedback

**Database and Models**
- Updated Task model to properly handle enum values
- Improved database migration process

### Documentation

**Agent Documentation**
- Updated developer, PM, QA, and Security agent documentation
- Added comprehensive agent role descriptions and workflows

### UI Improvements
- Added inline editing capabilities
- Enhanced proof-of-work system
- Improved security validation
- Added dedicated task list view
- Implemented expandable reports for agent details

## [Unreleased] - January 2026

### Core Refactor (bc7cfad)

**Major architectural simplification with PostgREST integration:**

- **PostgREST Service**: Added auto-generated REST API via PostgREST Docker service
- **Renamed Handoff → WorkCycle**: Clearer semantics for agent work sessions
- **Simplified Task States**:
  - Before: BACKLOG → PM → DEV → QA → SEC → DOCS → COMPLETE (with multiple failure states)
  - After: BACKLOG → IN_PROGRESS → VALIDATING → DONE
- **Removed Run-based Pipeline**: Pipeline stages now live on Tasks, not Runs
- **Claim Tracking**: Added claims_total, validated, failed columns to Task
- **WorkCycleService**: New service for task-centric work sessions
- **Core Flow**: Project → Task → WorkCycle → Claim validation → Ledger

### Job Queue System (0094c4f - 62635a5)

**Complete job queue for serialized LLM and agent execution:**

- **LLMJob Model**: Database-backed priority queue
  - Job types: llm_complete, llm_chat, llm_query, vision_analyze, agent_run
  - Statuses: pending, running, completed, failed, timeout, cancelled
  - Priority levels: CRITICAL(1), HIGH(2), NORMAL(3), LOW(4)
- **JobQueueService**: Enqueueing, dequeuing, status tracking
- **JobWorker**: Background threads processing queued jobs
  - LLM Worker: Handles completions and chat
  - Agent Worker: Handles Goose agent runs
  - Vision Worker: Handles image analysis
- **Queue Status Popover**:
  - Visual badge showing running/pending counts
  - Current job details with elapsed time
  - DMR (Docker Model Runner) health indicator
  - Pending jobs list with task links
  - Kill job functionality
- **Activity Log Page**: `/ui/activity/ for full job history

### API Endpoints Added

pass
- Simplify button functionality on task detail view
- `/api/tasks/{id}/simplify endpoint for converting complex descriptions into implementation steps
