# Dev Memory Backlog

## Seed Data Robustness

- [ ] YAML implicit scalar normalization: real seed entry validation exposed that
  human-written YAML can parse unquoted `created` / `updated` timestamps as
  datetime objects and values such as `error_codes: [-1]` as integers, while
  the schema expects strings. The current workaround is to quote those values
  when writing seed data. A future hardening pass should normalize these fields
  in `read_entry` or validation, converting datetime/int scalars to strings so
  real human and agent input is more robust.
