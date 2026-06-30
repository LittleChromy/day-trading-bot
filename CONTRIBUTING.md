# Contributing to Day Trading Bot

## Getting Started

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Development Guidelines

### Backend (Python)
- Follow PEP 8 style guide
- Use type hints where possible
- Write unit tests for new features
- Document complex functions with docstrings

### Frontend (React)
- Use functional components and hooks
- Follow React best practices
- Keep components modular and reusable
- Add PropTypes for component validation

## Running Tests

```bash
# Backend tests
cd backend
python -m pytest tests/

# Frontend tests
cd frontend
npm test
```

## Code Style

### Python
```bash
# Format code
black backend/

# Lint
pylint backend/
```

### JavaScript
```bash
# Format code
cd frontend
npx prettier --write src/

# Lint
npm run lint
```

## Reporting Issues

Include:
- Clear description of the bug
- Steps to reproduce
- Expected vs actual behavior
- System information (OS, Python/Node version, etc.)
- Screenshots/logs if applicable

## Feature Requests

Include:
- Clear description of the feature
- Use cases and benefits
- Potential implementation approach
- Any concerns or considerations

## Pull Request Process

1. Update documentation as needed
2. Add or update tests
3. Ensure all tests pass
4. Update CHANGELOG.md
5. Request review from maintainers
6. Address feedback and comments

## Code of Conduct

Be respectful, inclusive, and professional in all interactions.
