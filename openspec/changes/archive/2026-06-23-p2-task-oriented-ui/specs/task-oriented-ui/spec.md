## ADDED Requirements

### Requirement: Task-oriented Landing Page Grid
The system SHALL display 4 task cards ("Hỏi tài liệu", "Nghiên cứu web", "Phân tích file", "Tạo biểu mẫu") in a 2x2 grid layout on the main chat page for new chats instead of the standard suggestion list.

#### Scenario: Displaying task cards on new chat page
- **WHEN** the user opens a new chat session in OpenWebUI
- **THEN** the system displays 4 distinct cards in a 2x2 grid with dedicated icons, descriptions, and gradient styling

### Requirement: Task Card Triggering
The system SHALL route the user to a specialized model configuration or trigger a specific system prompt when a task card is clicked.

#### Scenario: Clicking on "Nghiên cứu web" task card
- **WHEN** the user clicks the "Nghiên cứu web" task card
- **THEN** the system launches a chat session pre-configured with the Web Search model and enters the corresponding template prompt
