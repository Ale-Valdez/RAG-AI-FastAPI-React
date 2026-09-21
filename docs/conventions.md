# Conventions

- Prefer explicit, maintainable designs. Keep responsibilities separated.
- Validate external inputs at boundaries. Keep configuration outside source code.
- Never commit secrets. Add tests with features.

## Python

- Type hints required.
- Domain logic is framework independent.
- Application layer coordinates use cases.
- Infrastructure implements ports.
- Tests accompany use cases.

## React

- TypeScript strict mode.
- Organize by feature.
- Separate API communication from presentation.
- Handle loading, empty, and error states.
