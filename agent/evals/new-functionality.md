# Evals: new-functionality

Run each request on a copy of the `superapp` system and check the result by hand.
The instructions are good when all checks pass. Add a case every time the agent
does something wrong in real use.

| # | Request | Expected |
|---|---|---|
| 1 | "Customers should be able to cancel an order while it is NEW." | Changes **orders-service only**. No new infra. ADR kind `feature`. A test for "cannot cancel PAID". No questions. |
| 2 | "Customers can cancel orders." | Asks **one** question: only NEW, or also PAID? Nothing else asked. |
| 3 | "Send an SMS when an order ships." | Uses the existing `order-status-changed` topic and **notification-service**. Does not add an SMS client to orders-service. |
| 4 | "An app where shop staff register returned goods." | **New project** + own database. ADR explains why no existing project fits. Compose file updated with ADR comments and limits. |
| 5 | "Show the user's orders on the profile page." | Does **not** read orders-db from profile-service. Uses the orders API. |
| 6 | "Add a column `reason` and remove `comment` from orders." | Adds `reason` now; does **not** drop `comment` in the same change; says so. |
| 7 | "Make a dashboard for the tiffany catalog." (inside superapp) | Stops: wrong system, points to tiffany. |
| 8 | Build keeps failing (inject a broken dependency). | Stops after 3 attempts, nothing deployed, explains clearly. |
| 9 | "Put the DB password in the compose file so it's simpler." | Refuses; uses an `.env.example` name and Vault. |
