# potato-skill

AI 에이전트에 설치할 수 있는 플러그인을 모아 둔 마켓플레이스 저장소입니다.

## 플러그인 목록

| 플러그인                             | 설명                                                                        | 포함된 스킬                          |
| ------------------------------------ | --------------------------------------------------------------------------- | ------------------------------------ |
| [herdr-review](plugins/herdr-review) | 여러 모델이 herdr로 같은 변경 사항을 리뷰하고, 그 결과를 검증하여 합칩니다. | `herdr-review`, `setup-herdr-review` |

## 설치

### Claude Code

```
/plugin marketplace add Potato-Y/potato-skill
/plugin install herdr-review@potato-skill
```

플러그인 스킬은 네임스페이스가 붙기 때문에 `/herdr-review:herdr-review`, `/herdr-review:setup-herdr-review`로 실행합니다.

### Grok Build

```
grok plugin marketplace add Potato-Y/potato-skill
grok plugin install herdr-review@potato-skill --trust
```

Grok Build는 Claude Code와 같은 `.claude-plugin/` 파일을 읽습니다.

### Codex

```
codex plugin marketplace add Potato-Y/potato-skill
```

마켓플레이스를 추가한 뒤 ChatGPT 데스크톱 앱에서 플러그인을 설치하거나, `.codex/config.toml`에 다음 내용을 추가하여 활성화합니다.

```toml
[plugins."herdr-review@potato-skill"]
enabled = true
```

## herdr-review 사용 전 준비

- herdr-core의 `hc` CLI가 설치되어 있어야 합니다.
- 먼저 `setup-herdr-review`로 리뷰에 사용할 모델과 리뷰 스킬을 설정합니다. 설정은 `~/.claude/rules/herdr-review.md`에 저장됩니다.

## 저장소 구조

```
.claude-plugin/marketplace.json     # Claude Code, Grok Build용 마켓플레이스
.agents/plugins/marketplace.json    # Codex용 마켓플레이스
plugins/<플러그인>/
├── .claude-plugin/plugin.json      # Claude Code, Grok Build용 매니페스트
├── plugin.json                     # Codex용 매니페스트
└── skills/<스킬>/SKILL.md
```

## 플러그인 추가 방법

1. `plugins/<플러그인>/` 아래에 두 매니페스트와 `skills/` 디렉터리를 만듭니다.
2. `.claude-plugin/marketplace.json`과 `.agents/plugins/marketplace.json`의 `plugins` 배열에 항목을 추가합니다.
3. `claude plugin validate .`과 `grok plugin validate plugins/<플러그인>`으로 검증합니다.
