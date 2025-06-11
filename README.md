# Repository Coverage



| Name                                        |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------------------- | -------: | -------: | ------: | --------: |
| backend/app/api/create\_task.py             |        9 |        0 |    100% |           |
| backend/app/api/exception\_handlers.py      |       26 |        4 |     85% |34, 55-56, 66 |
| backend/app/api/get\_task.py                |       16 |        5 |     69% |17-18, 22-24 |
| backend/app/api/routing.py                  |       13 |        0 |    100% |           |
| backend/app/api/v1/auth/get\_token.py       |       74 |       21 |     72% |40-52, 56-65, 122-153, 202-212, 257-266, 308-319 |
| backend/app/api/v1/auth/get\_user\_group.py |       73 |       39 |     47% |40, 54, 89-242 |
| backend/app/api/v1/auth/refresh\_token.py   |       69 |       45 |     35% |52-70, 88-103, 152-316 |
| backend/app/api/v1/models/auth.py           |       11 |        0 |    100% |           |
| backend/app/api/v1/models/errors.py         |        7 |        0 |    100% |           |
| backend/app/api/v1/models/resumes.py        |       24 |        0 |    100% |           |
| backend/app/api/v1/models/words.py          |        3 |        0 |    100% |           |
| backend/app/api/v1/observability/health.py  |      155 |      113 |     27% |78-195, 222-254, 279-323, 351-383, 394-411, 422, 431-441, 446-462 |
| backend/app/api/v1/resumes/status.py        |       35 |       25 |     29% |   193-241 |
| backend/app/api/v1/resumes/upload.py        |       67 |       47 |     30% |52-83, 96-123, 140-154, 309-399 |
| backend/app/api/v1/root.py                  |        8 |        0 |    100% |           |
| backend/app/api/v1/words/create.py          |       10 |        0 |    100% |           |
| backend/app/api/v1/words/delete.py          |        9 |        1 |     89% |        24 |
| backend/app/api/v1/words/get.py             |       12 |        0 |    100% |           |
| backend/app/auth/security\_hardening.py     |      217 |       85 |     61% |77-113, 118-123, 129-132, 190, 197, 227, 307, 330, 342, 346, 362-363, 373, 378-392, 404-417, 421-494, 498-502, 514-518 |
| backend/app/celery\_app.py                  |       52 |        8 |     85% |100-108, 115 |
| backend/app/config.py                       |      100 |       25 |     75% |26, 94, 96, 105, 107, 111, 118, 127, 131-145, 175, 184, 193, 202, 216, 225, 234 |
| backend/app/controllers/tasks.py            |       33 |        8 |     76% |28, 53, 59-64 |
| backend/app/controllers/words.py            |        2 |        1 |     50% |         2 |
| backend/app/db/security.py                  |      105 |       26 |     75% |122, 131, 140, 150-151, 191-225 |
| backend/app/db/session.py                   |       33 |        5 |     85% |54-55, 65-66, 102 |
| backend/app/json\_serializer.py             |        9 |        9 |      0% |     12-30 |
| backend/app/logging\_config.py              |       56 |        1 |     98% |        99 |
| backend/app/main.py                         |       37 |        5 |     86% |107-118, 125-127 |
| backend/app/middleware/observability.py     |       83 |       10 |     88% |242-243, 257-258, 271-272, 285-286, 301, 321 |
| backend/app/middleware/rate\_limiting.py    |       76 |        5 |     93% |94, 97, 174-201 |
| backend/app/modules\_load.py                |        9 |        0 |    100% |           |
| backend/app/observability/metrics.py        |      137 |       48 |     65% |133-138, 153, 238-252, 265-266, 279-303, 315-329, 334-350 |
| backend/app/security.py                     |        8 |        1 |     88% |        48 |
| backend/app/tasks/base.py                   |       33 |       16 |     52% |56-62, 86-94 |
| backend/app/tasks/debug.py                  |       21 |        9 |     57% | 11, 29-42 |
| backend/app/tasks/security.py               |      157 |       38 |     76% |188-209, 214, 226-237, 248, 259, 269, 347-348, 354-358, 362, 365, 370-373, 389-417 |
| backend/app/tasks/states.py                 |        2 |        0 |    100% |           |
| backend/app/tasks/words.py                  |       24 |       12 |     50% |     26-37 |
| backend/app/utils/password\_utils.py        |       18 |       18 |      0% |      5-44 |
| backend/app/validation/file\_validation.py  |      113 |       34 |     70% |18, 96-172, 239-247, 421-430, 492-539 |
| backend/app/validation/rate\_limiting.py    |      211 |        9 |     96% |256, 382, 408, 457, 482-483, 527, 567, 583 |
| backend/app/version.py                      |        1 |        0 |    100% |           |
| backend/app/workers/resume\_parser.py       |       99 |       31 |     69% |25-27, 32-34, 50-72, 88-110, 134 |
|                                   **TOTAL** | **2257** |  **704** | **69%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://github.com/sarmadashoor/fastapi-cellary/raw/python-coverage-comment-action-data/badge.svg)](https://github.com/sarmadashoor/fastapi-cellary/tree/python-coverage-comment-action-data)

This is the one to use if your repository is private or if you don't want to customize anything.



## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.