Язык: [English](README.md) | [Русский](README.ru.md)

# Проект Kerio Connect Logstash

Воспроизводимая лаборатория на базе Logstash и Elasticsearch: она принимает syslog Kerio Connect, раскладывает его по понятным полям и помогает проследить путь письма от приема до доставки.

[![CI](https://github.com/foksk76/kerio-logstash-project/actions/workflows/ci.yml/badge.svg)](https://github.com/foksk76/kerio-logstash-project/actions/workflows/ci.yml)

> **Статус проекта:** лабораторный проект для безопасной проверки парсинга логов Kerio Connect перед боевым использованием.

> **Языковая политика:** `README.md` — основной README на английском языке. `README.ru.md` — основной русский перевод для лабораторной работы и быстрого знакомства с проектом.

## Зачем нужен этот репозиторий

Kerio Connect умеет отправлять через syslog полезные операционные события, события безопасности и события доставки почты. Но в сыром виде такие логи неудобно искать, строить по ним графики и повторно проверять изменения парсера.

По смыслу здесь две задачи:

- принять живой syslog Kerio Connect, разобрать строки Kerio и сохранить их в Elasticsearch как структурированные события;
- дать локальную лабораторию, где можно проверить парсер, почтовые потоки и audit-события до подключения боевого сервера.

## Семейство проектов

Этот репозиторий является частью семейства проектов **Kerio Connect Monitoring & Logging**:

1. [kerio-connect](https://github.com/foksk76/kerio-connect) — воспроизводимое лабораторное окружение Kerio Connect
2. [kerio-logstash-project](https://github.com/foksk76/kerio-logstash-project) — пайплайн приема, парсинга и хранения Kerio syslog
3. [kerio-syslog-anonymizer](https://github.com/foksk76/kerio-syslog-anonymizer) — детерминированная анонимизация реальных логов для безопасной публикации

## Место репозитория в общей схеме

В общей цепочке этот репозиторий находится между Kerio Connect и интерфейсами просмотра:

`Kerio Connect -> Syslog (RFC5424) -> Logstash -> Elasticsearch -> Kibana / Grafana`

Репозитории дополняют друг друга:

- `kerio-connect` поднимает воспроизводимое лабораторное окружение Kerio Connect;
- `kerio-syslog-anonymizer` готовит реальные логи к безопасной публикации;
- этот репозиторий закрывает часть Logstash / Elasticsearch для Kerio syslog.

## Основной сценарий использования

Поток идет по цепочке от строк логов к структурированным данным:

1. Kerio Connect отправляет syslog на `5514/udp` или `5514/tcp`.
2. Logstash разбирает журналы Kerio `audit`, `security`, `warn`, `operations` и `mail` в поля, близкие к ECS.
3. Почтовые события `Recv` и `Sent` с общим `Queue-ID` собираются в один документ почтового потока.
4. Elasticsearch хранит исходные события и агрегированные почтовые потоки для поиска и просмотра.
5. Скрипты из репозитория запускают повторяемые проверки почты, audit-событий и результатов индексации.

## Для кого это

- Для администраторов Kerio Connect, которым нужно быстро понять, что происходило с почтой, входами и ошибками доставки.
- Для DevOps, observability и SecOps-инженеров, которым нужен небольшой стенд ELK для поиска, проверки и отладки логов Kerio.
- Для участников проекта, которые хотят менять парсер и сразу видеть, что именно изменилось в индексах и тестовых прогонах.

## Архитектура / Роли компонентов

Компоненты по ролям:

1. **Kerio Connect** отправляет RFC5424 syslog на порт `5514`.
2. **Logstash** разбирает syslog-обертку и применяет правила Kerio из `logstash/pipeline/kerio-connect-main.conf`.
3. **Elasticsearch** хранит два вида данных: исходные события в `kerio-connect-*` и почтовые потоки в `kerio-flow-*`.
4. **Kibana / Grafana** дают интерфейс для поиска, просмотра и будущих дашбордов.
5. **Скрипты в `scripts/`** создают тестовых пользователей, отправляют письма и проверяют, что события дошли до индексов.

## Требования

### Программное обеспечение

- Debian, Ubuntu или другое Linux-окружение с поддержкой Docker
- Docker Engine
- плагин Docker Compose
- `curl`
- `python3` для локального примера проверки и вспомогательных скриптов
- хост Kerio Connect, если нужны реальные логи Kerio вместо синтетических событий

### Аппаратные ресурсы

- минимум 2 vCPU
- 6 GB RAM, доступной Docker, как практический минимум для настроек по умолчанию
- 10 GB свободного места на диске для образов, данных Elasticsearch и логов

### Проверенные версии

| Компонент | Версия | Примечания |
|---|---|---|
| OS | Debian GNU/Linux 13 (trixie) | Текущее окружение сопровождающего проекта |
| Python | 3.13.5 | Используется для вспомогательных скриптов и синтетических тестовых данных |
| Docker Engine | 28.2.2 | Проверенная рабочая версия |
| Docker Compose | 2.37.1 | Проверенная рабочая версия |
| Elasticsearch | 8.19.11 | Задано в `docker-compose.yml` |
| Logstash | 8.19.11 | Задано в `docker-compose.yml` |
| Kibana | 8.19.11 | Задано в `docker-compose.yml` |

## Структура репозитория

Если нужно быстро найти нужное место:

- `docker-compose.yml` поднимает локальный стек Elasticsearch, Logstash и Kibana.
- `logstash/pipeline/kerio-connect-main.conf` — главный пайплайн парсинга Kerio.
- `logstash/config/` содержит настройки Logstash и список пайплайнов.
- `elasticsearch/templates/` хранит шаблоны индексов для `kerio-connect-*` и `kerio-flow-*`.
- `docker/kibana/` содержит служебные скрипты для старта Kibana со служебным токеном.
- `scripts/` содержит инструменты прогона: генерацию тестовых пользователей, отправку писем, audit matrix и проверку результатов.
- `artifacts/runs/` — место для локальных артефактов прогонов; его содержимое не нужно коммитить.
- `README.md`, `README.ru.md`, `CHANGELOG.md`, `HANDOFF.md` и `NEXT_STEPS.md` описывают текущее состояние проекта и дальнейшие шаги.

## Языковая политика документации

- `README.md` — основной источник на английском языке.
- `README.ru.md` — основной русский перевод для лабораторной работы и быстрого знакомства с проектом.
- Первая строка обоих README-файлов — переключатель языка.
- Русский README следует английскому README и не описывает отдельное поведение.
- `CHANGELOG.md` ведется на английском языке.
- `CONTRIBUTING.md` ведется на английском языке; русские правки README допустимы, если они сохраняют смысл английской версии.

## Быстрый старт

Короткий путь: поднять локальный стек, отправить одно тестовое событие и увидеть его в Elasticsearch.

В результате вы:

- запустите стек ELK;
- убедитесь, что пайплайн Logstash загружен;
- отправите одно syslog-событие в Logstash;
- увидите распарсенное Kerio-событие в Elasticsearch.

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/foksk76/kerio-logstash-project.git
cd kerio-logstash-project
```

Если все хорошо:

- текущая директория является корнем репозитория;
- присутствуют файлы вроде `docker-compose.yml` и `README.md`.

### 2. Подготовьте окружение

Создайте `.env` с паролем Elasticsearch для этого стека:

```bash
cat > .env <<'EOF'
ELASTIC_PASSWORD=ChangeMe-2026!
EOF
```

Что можно изменить:

- замените `ChangeMe-2026!`, если не хотите оставлять примерный пароль;
- имя переменной должно оставаться ровно `ELASTIC_PASSWORD`.

Что важно:

- `.env` должен существовать до запуска `docker compose up -d`;
- тот же пароль должен использоваться во всех командах `curl -u elastic:$ELASTIC_PASSWORD ...` ниже.

Необязательные настройки для живых тестовых прогонов Kerio:

```bash
KERIO_API_USER=admin@example.test
KERIO_API_PASSWORD=ChangeMe-2026!
```

`scripts/generate_identities.py` использует эти значения, когда тестовым инструментам нужно автоматически создавать и сбрасывать управляемые Kerio-ящики через административный API.

Что проверить перед первым стартом:

- `docker-compose.yml` сейчас задает `ES_JAVA_OPTS=-Xms2g -Xmx2g` и `LS_JAVA_OPTS=-Xms1g -Xmx1g`;
- если ваш Docker-хост не может выделить столько памяти, уменьшите эти значения в `docker-compose.yml` до старта стека.

### 3. Запустите проект

Запустите стек:

```bash
docker compose up -d
```

Установите шаблоны индексов Elasticsearch:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD -H "Content-Type: application/json" \
  -X PUT http://localhost:9200/_index_template/kerio-connect-ecs \
  --data-binary @elasticsearch/templates/kerio-connect-ecs-template.json

curl -s -u elastic:$ELASTIC_PASSWORD -H "Content-Type: application/json" \
  -X PUT http://localhost:9200/_index_template/kerio-flow-template \
  --data-binary @elasticsearch/templates/kerio-flow-template.json
```

Если все хорошо:

- `docker compose up -d` создает и запускает `kerio-elasticsearch`, `kerio-logstash` и `kerio-kibana`;
- `kibana-token-init` запускается один раз и успешно завершается;
- каждая команда установки шаблона возвращает JSON с `"acknowledged": true`.

Если подключаете живой Kerio:

- для реальных логов Kerio настройте внешний syslog в Kerio Connect на отправку в `<elk-host>:5514`;
- для этого быстрого старта Kerio-хост не нужен: на шаге 4 локально отправляется одно синтетическое RFC5424-событие.

### 4. Проверьте результат

Проверьте состояние контейнеров:

```bash
docker compose ps
```

Если все хорошо:

- `kerio-elasticsearch` находится в состоянии `Up` и `healthy`;
- `kerio-logstash` находится в состоянии `Up`;
- `kerio-kibana` находится в состоянии `Up`;
- `kibana-token-init` показывает `Exited (0)`, если он все еще отображается.

Проверьте, что Elasticsearch отвечает:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200 | python3 -m json.tool
```

Если все хорошо:

- JSON содержит `"cluster_name": "kerio-es"`;
- запрос проходит без ошибки аутентификации.

Проверьте, что пайплайн Logstash загружен:

```bash
curl -s http://localhost:9600/_node/pipelines?pretty
```

Если все хорошо:

- вывод содержит `kerio-connect-main`;
- в ответе нет критической ошибки.

Отправьте одно синтетическое RFC5424-событие в стиле Kerio в локальный UDP-вход:

```bash
python3 - <<'PY'
import socket

message = (
    "<21>1 2026-04-05T00:00:00Z kerio-connect kerio - - - "
    "Attempt to deliver to unknown recipient <ghost.user.001@example.test>, "
    "from <sender@example.test>, IP address 192.0.2.10\n"
)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(message.encode("utf-8"), ("127.0.0.1", 5514))
sock.close()
PY
```

Если все хорошо:

- команда завершается без вывода;
- Logstash принимает пакет на `5514/udp`.

Проверьте, что Elasticsearch получил распарсенное событие:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD \
  "http://localhost:9200/kerio-connect-*/_search?pretty" \
  -H "Content-Type: application/json" \
  -d '{"size":1,"sort":[{"@timestamp":{"order":"desc"}}],"query":{"term":{"event.action":"delivery_unknown_recipient"}},"_source":["@timestamp","event.action","event.outcome","email.from.address","email.to.address","kerio.result","network.protocol"]}'
```

Если все хорошо:

- возвращается документ из `kerio-connect-*`;
- `event.action` равен `delivery_unknown_recipient`;
- `event.outcome` равен `failure`;
- `email.from.address` равен `sender@example.test`;
- `email.to.address` равен `ghost.user.001@example.test`;
- `kerio.result` равен `not_delivered`.

### 5. Зафиксируйте итог

После шагов выше у вас должны остаться:

- запущенный стек ELK;
- загруженный пайплайн Logstash;
- минимум один распарсенный документ в `kerio-connect-*`.

Проверить существование индекса можно так:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/_cat/indices/kerio-*?v
```

Если все хорошо:

- отображается минимум один индекс `kerio-connect-YYYY.MM.DD`;
- исходный индекс имеет ненулевой `docs.count` после синтетического тестового события;
- Kibana доступна по адресу `http://localhost/`.

## Проверка Audit Matrix

Для прогона audit-событий Kerio в репозитории есть `scripts/run_audit_matrix.py`.
Скрипт читает существующий `identities.json`, проходит доступные пути входа в Kerio и проверяет успешные записи аутентификации напрямую в `audit.log` по SSH.

Запускайте этот сценарий, когда у вас уже есть живой Kerio Connect, доступ к нему по SSH и готовый `identities.json` из предыдущего прогона. Для первого знакомства с проектом он не нужен: быстрый старт выше специально обходится без живого Kerio-хоста.

Текущая автоматическая матрица покрывает:

- `HTTP/WebAdmin` через Kerio admin JSON-RPC API;
- `HTTP/WebMail` через Kerio client JSON-RPC API;
- `SMTP` через аутентифицированную отправку на `587`;
- `IMAP` через `993`;
- `POP3` через `995`.

`HTTP/KOFF` остается ручным кейсом в результате прогона, потому что для него на стенде нужен Kerio Outlook Connector / Outlook.

Пример:

```bash
python3 scripts/run_audit_matrix.py \
  --run-id AUDIT-MATRIX-20260406 \
  --identities-file artifacts/runs/LIVE-PLUS10-20260406-124549/identities.json \
  --output-dir artifacts/runs/AUDIT-MATRIX-20260406/audit
```

Ожидаемые артефакты:

- `audit_results.json` с результатами pass / fail / skip по каждому протоколу;
- `audit_summary.md` с читаемой сводкой по матрице.

## Минимальный пример события

Следующая RFC5424-строка является минимальным рабочим примером:

```text
<21>1 2026-04-05T00:00:00Z kerio-connect kerio - - - Attempt to deliver to unknown recipient <ghost.user.001@example.test>, from <sender@example.test>, IP address 192.0.2.10
```

## Нормализованный результат

Ожидаемый документ в Elasticsearch выглядит так:

```json
{
  "@timestamp": "2026-04-05T00:00:00.000Z",
  "event": {
    "category": "email",
    "type": "denied",
    "action": "delivery_unknown_recipient",
    "outcome": "failure",
    "reason": "unknown_recipient"
  },
  "process": {
    "name": "kerio"
  },
  "network": {
    "protocol": "smtp"
  },
  "email": {
    "from": {
      "address": "sender@example.test"
    },
    "to": {
      "address": "ghost.user.001@example.test"
    }
  },
  "kerio": {
    "result": "not_delivered"
  }
}
```

## Чеклист проверки

- [ ] Репозиторий успешно клонирован
- [ ] `.env` создан с `ELASTIC_PASSWORD`
- [ ] `docker compose up -d` завершился успешно
- [ ] шаблоны Elasticsearch установлены с `"acknowledged": true`
- [ ] `docker compose ps` показывает здоровый Elasticsearch и запущенные Logstash/Kibana
- [ ] `curl http://localhost:9600/_node/pipelines?pretty` показывает `kerio-connect-main`
- [ ] синтетическое или живое событие Kerio появляется в `kerio-connect-*`
- [ ] распарсенные поля совпадают с задокументированным примером

## Устранение неполадок

### Проблема: Elasticsearch завершается или постоянно перезапускается

**Симптомы**

- `docker compose ps` показывает, что `kerio-elasticsearch` перезапускается или завершен;
- `docker compose logs elasticsearch` упоминает нехватку памяти или код выхода `137`.

**Что проверить**

- настройка heap по умолчанию слишком велика для памяти, доступной Docker.

**Как исправить**

Пример исправления для небольшого лабораторного хоста:

```bash
sed -i 's/ES_JAVA_OPTS=-Xms2g -Xmx2g/ES_JAVA_OPTS=-Xms1g -Xmx1g/' docker-compose.yml
docker compose up -d
```

Если все хорошо:

- `kerio-elasticsearch` остается запущенным;
- `curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200` возвращает JSON вместо ошибки соединения.

### Проблема: пайплайн запущен, но события не появляются в `kerio-connect-*`

**Симптомы**

- `curl http://localhost:9600/_node/pipelines?pretty` показывает `kerio-connect-main`;
- пример `_search` возвращает ноль результатов.

**Что проверить**

- до `5514` ничего не дошло, или тестовое событие было отправлено до полного старта Logstash.

**Как исправить**

```bash
docker compose logs --tail 50 logstash
curl -s http://localhost:9600/_node/pipelines?pretty | grep kerio-connect-main
```

Затем повторно отправьте синтетическое событие из шага `4` быстрого старта и снова выполните команду `_search`.

Если все хорошо:

- Logstash запущен и слушает входящие события;
- следующий поиск возвращает распарсенный документ.

### Проблема: Kibana открывается, но ссылки указывают на неправильный URL или порт

**Симптомы**

- Kibana доступна локально, но сгенерированные ссылки или перенаправления используют неправильный публичный URL.

**Что проверить**

- `docker-compose.yml` публикует Kibana на порту хоста `80`, а `SERVER_PUBLICBASEURL` может требовать соответствия реальному внешнему URL.

**Как исправить**

Отредактируйте `docker-compose.yml`, затем перезапустите Kibana:

```bash
docker compose up -d kibana
```

Если все хорошо:

- Kibana остается доступной;
- публичный базовый URL соответствует вашему окружению.

## Что проект не делает

- Этот репозиторий не разворачивает Kerio Connect. Он предполагает, что логи приходят из уже существующего источника Kerio.
- Этот репозиторий не заменяет документацию вендора.
- Этот репозиторий не является полным руководством по production hardening для Elastic Stack или Kerio Connect.
- Этот репозиторий по умолчанию не поставляет готовые дашборды или материалы для Grafana.
- Этот репозиторий не предназначен для анонимизации реальных клиентских логов. Для этого используйте `kerio-syslog-anonymizer`.

## Что важно знать

- Kerio Connect — проприетарное ПО вендора; этот репозиторий его не распространяет.
- Docker-образы Elastic Stack являются сторонним ПО и регулируются собственными лицензиями и условиями использования.
- Пайплайн Logstash намеренно использует `pipeline.workers: 1`, потому что агрегация почтовых потоков зависит от фильтра `aggregate`.
- Kibana сейчас опубликована на порту хоста `80`, поэтому локальный URL по умолчанию — `http://localhost/`.
- `artifacts/runs/` может содержать сгенерированные пароли, тестовых получателей и результаты проверок. Держите эти файлы локально и вне git.
- `.env` намеренно игнорируется, потому что содержит секреты времени выполнения вроде `ELASTIC_PASSWORD`, `KERIO_API_USER` и `KERIO_API_PASSWORD`.

## Roadmap

См. [NEXT_STEPS.md](./NEXT_STEPS.md)

## Changelog

См. [CHANGELOG.md](./CHANGELOG.md)

Оставляйте `CHANGELOG.md` каноническим журналом изменений на английском языке, если репозиторий явно не решит иначе.

## Handoff

См. [HANDOFF.md](./HANDOFF.md)

## Участие в проекте

См. [CONTRIBUTING.md](./CONTRIBUTING.md)

Английский язык остается основным языком проектной документации и ревью. Обновления русского README приветствуются, но они должны следовать английскому README и сохранять то же задокументированное поведение.

## GitHub Release Notes

GitHub Release Notes должны оставаться на английском языке и писаться для DevOps-инженеров, системных администраторов и операторов.

Фокус release notes — на том, что изменилось для человека, который запускает и обслуживает проект:

- изменения, которые можно запустить, наблюдать, проверить или диагностировать;
- влияние на прием логов, парсинг, дашборды, скрипты, развертывание, проверки или создаваемые артефакты;
- точные команды проверки, ID живых прогонов, статус CI и ожидаемые числа pass/fail;
- заметки по обновлению, обязательные действия оператора, известные ограничения и ручные шаги.

Избегайте подробного перечисления файлов и внутренних изменений, если они не меняют способ использования проекта операторами.

## Безопасность

См. [SECURITY.md](./SECURITY.md)

## Поддержка

См. [SUPPORT.md](./SUPPORT.md)

## Лицензия

См. [LICENSE](./LICENSE)
