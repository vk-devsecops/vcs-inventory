## Все репозитории, к которым имеет доступ пользователь

Запрос:

```sql
SELECT repository.web_url,
	repository.is_scanned,
	repository.visibility,
	repository.last_activity_repo,
	repository_user.access_level
FROM repository_user
INNER JOIN repository ON repository.vcs_id = repository_user.repo_id
INNER JOIN users users ON (
		users.vcs_instance_id = repository_user.vcs_instance_id
		AND users.vcs_id = repository_user.user_id
		)
WHERE users.username = 'a.leksandr';
```

Пример ответа:

```bash
                       web_url                       | is_scanned | visibility |   last_activity_repo    | access_level 
-----------------------------------------------------+------------+------------+-------------------------+--------------
 https://gitlab.mycompany.com/frontend/nodejs        | f          | internal   | 2024-11-12 12:01:11.642 | developer
 https://gitlab.mycompany.com/frontend/deps          | f          | internal   | 2024-11-26 08:14:02.569 | maintainer
 https://bitbucket.mycompany.com/soc/pineapple       | f          | internal   | 2024-11-25 15:49:20.014 | reporter
```


## Все пользователи репозитория

Запрос:

```sql
SELECT users.username,
	repository_user.access_level
FROM repository_user
INNER JOIN repository ON (
		repository.vcs_instance_id = repository_user.vcs_instance_id
		AND repository.vcs_id = repository_user.repo_id
		)
INNER JOIN users ON (
		users.vcs_instance_id = repository_user.vcs_instance_id
		AND users.vcs_id = repository_user.user_id
		)
WHERE repository.web_url = 'https://gitlab.mycompany.com/backend/python'
ORDER BY access_level;
```

Пример ответа:

```bash
      username       | access_level 
---------------------+--------------
 a.leksandr          | guest
 b.oris              | developer
 d.enis              | maintainer
```

## Все репозитории, в которые контрибьютил пользователь

Запрос:


```sql
SELECT repository.web_url,
	contributors.commits
FROM contributors
INNER JOIN repository ON (
		repository.vcs_instance_id = contributors.vcs_instance_id
		AND repository.vcs_id = contributors.repo_id
		)
WHERE email = 'd.enis@mycompany.com';
```

Пример ответа:

```bash
                            web_url                            | commits 
---------------------------------------------------------------+---------
 https://gitlab.mycompany.com/backend/task-service             |     128
 https://gitlab.mycompany.com/backend/vk-support-messeger      |      64
 https://bitbucket.mycompany.com/infra/ansible                 |      32
```


## Все активные репозитории (в которых была активность за последний год)

Запрос:

```sql
SELECT web_url,
	visibility
	default_branch
	is_scanned
	last_commit_at
FROM repository
WHERE (CURRENT_TIMESTAMP - last_activity_repo) < '1 year'::interval;
```

Пример ответа:

```bash
web_url                                             | visibility | default_branch | is_scanned |   last_commit_at    
----------------------------------------------------+------------+----------------+------------+---------------------
 https://bitbucket.mycompany.com/frontend/prod/     | private    | main           | f          | 2024-11-11 10:24:40
 https://gitlab.mycompany.com/backend/golang/       | private    | master         | f          | 2024-11-25 22:56:24
 https://gitlab.mycompany.com/infra/ansible/        | internal   | master         | f          | 2024-11-15 10:34:26
```