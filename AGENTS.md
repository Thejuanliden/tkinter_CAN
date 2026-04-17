# Agent Coding Guidelines

This document provides guidelines for AI agents working on this codebase.

## Project Overview

- **Name**: tkinter-can
- **Type**: Tkinter-based J1939 CAN bus control panel application
- **Python**: 3.14+
- **Dependencies**: cantools>=41.3.0, python-can>=4.6.1

## Build, Lint, and Test Commands

### Running the Application
```bash
python main.py
```

### Package Installation
```bash
pip install -e .
pip install cantools python-can
```

### Linting and Formatting
This project uses Ruff for linting. Install and run:
```bash
pip install ruff
ruff check .        # Run linter
ruff format .       # Format code
```

### Running a Single Test
No test framework is currently configured. To add tests:
```bash
pip install pytest
pytest tests/                    # Run all tests
pytest tests/test_file.py::TestClass::test_method  # Run single test
```

## Code Style Guidelines

### Imports
- Group imports in order: standard library, third-party, local
- Use explicit relative imports for local modules
- Example:
  ```python
  import threading
  import logging
  from typing import Dict, Optional, Callable, Any
  
  import can
  from can import Listener
  
  from can_types import CANMessageType, DecodedMessage
  ```

### Formatting
- Maximum line length: 100 characters (Ruff default)
- Use 4 spaces for indentation (not tabs)
- Use blank lines sparingly to group related code (max 2 consecutive)
- No trailing whitespace

### Types
- Use type hints for all function arguments and return values
- Use `Optional[X]` instead of `X | None` for compatibility
- Use concrete types: `Dict`, `List`, `Set` (not shorthand)
- Example:
  ```python
  def connect(self, channel: int, baudrate: int = 250000) -> bool:
      ...
  ```

### Naming Conventions
- **Classes**: PascalCase (e.g., `CANService`, `DecodedMessage`)
- **Functions/Methods**: snake_case (e.g., `start_listening`, `_handle_message`)
- **Private methods**: prefix with underscore (e.g., `_log`, `_on_message`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `PGN_DM1`, `CAN_ID_DM1`)
- **Variables**: snake_case (e.g., `dbc_path`, `is_listening`)

### Error Handling
- Use specific exception types when possible
- Log errors before returning False or raising
- Example:
  ```python
  try:
      self.bus = can.interface.Bus(...)
      return True
  except Exception as e:
      self._log(f"Connection error: {e}")
      return False
  ```

### Data Classes
- Use `@dataclass` for simple data containers
- Use `field(default_factory=list)` for mutable defaults
- Example:
  ```python
  @dataclass
  class DecodedMessage:
      timestamp: float
      can_id: int
      message_type: CANMessageType
      raw_data: bytes
      decoded_fields: Dict[str, Any] = field(default_factory=dict)
      dbc_name: Optional[str] = None
      is_update: bool = True
  ```

### Threading and Concurrency
- Use `threading.Lock()` for shared state
- Use daemon threads for background tasks
- Always join threads with timeout in cleanup code

### GUI Code (Tkinter)
- Use `root.after(0, callback)` for thread-safe GUI updates
- Use `ttk` widgets for consistent styling
- Bind cleanup to `WM_DELETE_WINDOW` protocol

### General Patterns
- Keep classes focused (single responsibility)
- Add docstrings for public methods
- Use logging instead of print statements
- Avoid global state; use class instances
- Private attributes prefixed with underscore