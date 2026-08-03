# Dummy customers (red-team only)

| Id | Persona | Use |
|---|---|---|
| dummy-angry | Chargeback threat | P0 payment path |
| dummy-doublebook | Wants overlapping slots | booking conflict |
| dummy-lyrics | Pastes famous chorus | IP denylist |
| dummy-callme | Insists on phone | phone queue |
| dummy-cash | Pays cash at booth | cash queue |
| dummy-consent | Portrait post ask | consent checklist |

Never mix dummy traffic into real shop stats without a `test:` prefix.
