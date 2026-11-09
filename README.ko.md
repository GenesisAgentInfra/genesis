<p align="center">
  <a href="https://usegenesis.vercel.app/"><img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle"></a>&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h1 align="center">에이전트의 모든 변경을 위한 가드레일.</h1>

<p align="center">
  <a href="https://usegenesis.vercel.app/">공식 웹사이트</a> &nbsp;·&nbsp;
  <a href="#genesis-get-started"><strong>시작하기</strong></a> &nbsp;·&nbsp;
  <a href="#genesis-docs">문서</a> &nbsp;·&nbsp;
  <a href="#genesis-stars">스타 기록</a>
</p>

<p align="center"><a href="README.md">English</a> &nbsp;·&nbsp; <a href="README.zh-CN.md">简体中文</a> &nbsp;·&nbsp; <a href="README.ja.md">日本語</a> &nbsp;·&nbsp; <strong>한국어</strong> &nbsp;·&nbsp; <a href="README.de.md">Deutsch</a> &nbsp;·&nbsp; <a href="README.fr.md">Français</a> &nbsp;·&nbsp; <a href="README.es.md">Español</a></p>

<p align="center">
  <a href="https://github.com/GenesisAgentInfra/genesis-cli/stargazers"><img src="https://img.shields.io/github/stars/GenesisAgentInfra/genesis-cli?style=flat-square&amp;logo=github&amp;label=Stars&amp;color=e3b341" alt="GitHub Stars" height="24"></a>
  <a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/LICENSE"><img src="https://img.shields.io/github/license/GenesisAgentInfra/genesis-cli?style=flat-square&amp;color=34a853" alt="License: Apache-2.0" height="24"></a>
  <a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md"><img src="https://img.shields.io/static/v1?label=works+with&amp;message=Codex+%7C+Claude+Code&amp;color=7c3aed&amp;style=flat-square" alt="Works with Codex and Claude Code" height="24"></a>
  <a href="https://github.com/GenesisAgentInfra/genesis-cli#what-your-review-covers"><img src="https://img.shields.io/static/v1?label=analyzes&amp;message=Python&amp;logo=python&amp;logoColor=white&amp;color=3776ab&amp;style=flat-square" alt="Supported analysis language: Python" height="24"></a>
  <a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/packages/genesis_ci/pyproject.toml"><img src="https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2FGenesisAgentInfra%2Fgenesis-cli%2Fmain%2Fpackages%2Fgenesis_ci%2Fpyproject.toml&amp;query=%24.project.version&amp;label=version&amp;color=0891b2&amp;style=flat-square" alt="CLI package version" height="24"></a>
</p>

<p align="center">
  <a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md">
    <picture>
      <source media="(max-width: 600px) and (prefers-reduced-motion: reduce)" srcset="assets/readme/code-intelligence-animation-mobile-poster.png">
      <source media="(max-width: 600px)" srcset="assets/readme/code-intelligence-animation-mobile.gif">
      <source media="(prefers-reduced-motion: reduce)" srcset="assets/readme/code-intelligence-animation-poster.png">
      <img src="assets/readme/code-intelligence-animation.gif" alt="코드 리뷰 흐름을 보여 주는 애니메이션: Python 코드 변경에서 맥락, 동작, 위험 분석을 거쳐 리뷰 보고서를 생성합니다." width="100%">
    </picture>
  </a>
</p>

<p align="center"><sub><a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md">코드 리뷰 흐름 예시</a></sub></p>

## Genesis가 필요한 이유

코드 변경이 사용자에게 전달되는 결과를 어떻게 바꾸는지 확인하세요.

| 사용자에게 미치는 영향 | Genesis가 검토를 돕는 내용 |
| --- | --- |
| **에이전트는 계속 일하지만, 결과는 오지 않습니다.** [출처](https://github.com/openai/openai-agents-python/issues/191) | 작업 완료 조건과 종료 조건의 변경. |
| **사용자가 거절해도 작업이 실행됩니다.** [출처](https://github.com/langchain-ai/langchain/issues/40492) | 승인 검사와 작업 실행 경로의 변경. |
| **요청은 한 번인데, 같은 작업이 두 번 실행됩니다.** [출처](https://github.com/langchain-ai/langgraph/issues/9185) | 재시도 경로와 중복 작업 방지 검사. |

공개 보고와 재현 사례에 기반하며, Genesis 탐지 성능 평가 결과는 아닙니다.
[근거와 지원 범위](docs/research/agent-change-pain-points.md).

<a id="genesis-get-started"></a>

## 코딩 에이전트에서 시작하기

CLI와 정적 분석은 오픈 소스입니다. 의미 분석을 포함한 리뷰는 Genesis 호스팅 서비스를 사용하며, 소스 코드를 보내기 전에 사용자의 승인을 받습니다.

### 1. 처음 한 번 설치하기

리뷰할 프로젝트에서 Codex 또는 Claude Code를 열고 다음 요청을 붙여 넣으세요.

```text
https://github.com/GenesisAgentInfra/genesis-cli 에서 Genesis를 설정해 주세요.
README와 docs/coding-agents.md를 읽고 CLI는 프로젝트 밖에, genesis-review skill은
현재 에이전트의 사용자 범위에 설치하세요. 기존 설치를 재사용하고 수정되지 않은 관리형 skill은 필요하면 갱신하세요.
docs/coding-agents.md의 "Configure CR preparation in this project"에 따라 기존 내용을 보존하면서
이 프로젝트의 에이전트 지침에 CR/PR 준비 전에 Genesis를 실행하는 규칙을 추가하세요.
CLI, skill, 프로젝트 지침을 확인하고 변경한 파일을 알려 주세요.
지금은 설정만 하고 코드 분석이나 업로드는 하지 마세요. 향후 업로드에도 대상 서비스와 선택된 소스를 포함하는 승인이 필요합니다.
```

**설정 후:** “이 변경 사항을 코드 리뷰에 올릴 준비를 해 줘”라고 요청하면 프로젝트 지침에 따라
에이전트가 CR/PR 설명을 완성하기 전에 Genesis를 실행하고 결과를 설명합니다. GitHub CI는 필요하지 않습니다.
이는 에이전트 지침이며 실행 보장, Git hook 또는 병합 차단 기능이 아닙니다. skill은 사용자 범위에 설치되지만
이 규칙은 현재 프로젝트에만 적용됩니다. CLI 설치만으로는 추가되지 않습니다.
[수동 설정, 업데이트 및 제거](docs/coding-agents.md#configure-cr-preparation-in-this-project).

<details>
<summary>직접 설치하기</summary>

리뷰할 애플리케이션의 외부에서 다음 명령을 실행하세요.

```sh
git clone https://github.com/GenesisAgentInfra/genesis-cli.git
cd genesis-cli
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis version
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent codex
uv run --package genesis-ci --no-dev --frozen genesis agent status --agent codex
```

</details>

### 2. 리뷰 요청하기

```text
이 변경 사항을 CR/PR에 올릴 준비를 해 주세요. 프로젝트의 Genesis 리뷰 지침에 따라
분석 결과와 미검증 사항을 설명한 뒤 리뷰 설명을 완성하세요. 전송 전에 업로드 범위를 보여 주세요.
```

스킬을 직접 선택할 수도 있습니다.

| 에이전트 | 호출 방법 |
| --- | --- |
| Codex | `$genesis-review` 뒤에 요청 입력 |
| Claude Code | `/genesis-review` 뒤에 요청 입력 |

다른 범위를 리뷰하려면 비교할 브랜치나 커밋 쌍을 지정하세요. 작업 설명과 흐름도는 필요에 따라 추가할 수 있는 컨텍스트입니다.

개인 연결 설정이 없으면 `genesis auth` 없이 공식 공유 체험판을 사용할 수 있습니다. 사용량은 모든 사용자가 함께 쓰는 제한된 할당량에서 차감됩니다. 모델 제공업체의 API 키는 필요하지 않습니다.
[접근 방법 및 체험판 제한](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md#default-shared-trial).

## 리뷰에서 확인하는 내용

| 영역 | 제공하는 정보 |
| --- | --- |
| 비즈니스 동작 | 애플리케이션의 동작이 어떻게 달라질 수 있는지 보여 주는 변경 전후의 근거. |
| 영향을 받는 경로 | 변경과 연결된 호출자 및 코드 경로, 그리고 제공된 흐름도. |
| 비용, 대기, 실패 | 확보된 근거가 뒷받침하는 범위 내에서 제시하는 조건부 위험과 정적 추정치. |
| 테스트 | 관련 테스트 소스가 무엇을 확인하는지, 어떤 검증문이 누락되었을 수 있는지. |
| 검증 | 권장 확인 사항과 추가 근거가 필요한 부분. |

## 변경 사항에서 보고서까지

1. **로컬에서 준비합니다.** Genesis가 선택한 변경 사항을 캡처하고 코드 근거를 추출합니다. 에이전트가 업로드 대상으로 선택된 소스 발췌문과 사실 정보를 보여 줍니다.
2. **업로드를 승인합니다.** 사용자가 허용하면 Genesis가 해당 자료를 호스팅 서비스로 보냅니다. 분석을 로컬로 제한하고 부분 보고서를 받을 수도 있습니다.
3. **채팅에서 결과를 확인합니다.** 에이전트가 보고서를 설명하고, 근거와 상태를 확인하며, 추가 검증이 필요한 부분을 짚어 줍니다.

보고서는 프로젝트의 `.genesis/analyses/<run-id>/`에 저장됩니다.

- `summary.md`: 읽기 쉬운 요약부터 확인하세요.
- `report.md`: 상세한 발견 사항, 근거, 상태를 확인할 수 있습니다.
- `report.json`: 구조화된 결과를 자신의 도구에서 활용할 수 있습니다.

종료 코드 **0**은 명시된 범위 내에서 완료되었음을, **2**는 사용 가능한 부분 보고서가 생성되었음을, **1**은 요청한 결과를 생성하지 못했음을 뜻합니다. `.genesis/`에는 캡처한 소스가 포함될 수 있으므로 Git에 추가하지 마세요.

## 소스 코드와 서비스

공개 저장소에는 CLI와 정적 분석이 포함되어 있습니다. 비공개 의미 분석 서비스는 Genesis 팀이 운영하며, 직접 호스팅할 수 있는 서버 구현은 포함되어 있지 않습니다.

미리보기와 오프라인 분석은 로컬에서만 수행됩니다. 스킬을 설치해도 매번 편집할 때마다 리뷰가 자동으로 실행되지는 않습니다.

[데이터 처리, 개인 키 및 설정](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md).

<a id="genesis-docs"></a>

## 문서

- [코딩 에이전트 가이드](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md): 설정, 스킬 검색, 팀 지침 및 문제 해결.
- [CLI 가이드](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md): 명령, 선택적 컨텍스트, 자격 증명 및 데이터 처리.
- [GitHub Action](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/github-action.md): 저장소 자동화를 설정합니다. 호스팅 분석에는 Genesis 키를 명시적으로 설정해야 합니다.
- [기여 가이드](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/CONTRIBUTING.md): 클라이언트 개발 및 테스트.
- [저장소 범위](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/repository-boundary.md)와 [보고서 스키마](https://github.com/GenesisAgentInfra/code-intelligence-protocol).

<a id="genesis-stars"></a>

## 스타 기록

<a href="https://www.star-history.com/#GenesisAgentInfra/genesis-cli&amp;Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date&amp;theme=dark">
    <img src="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date" alt="GenesisAgentInfra/genesis-cli의 스타 기록" width="100%">
  </picture>
</a>

[Star History에서 보기](https://www.star-history.com/#GenesisAgentInfra/genesis-cli&Date)


## 라이선스

Genesis CLI의 자체 코드는 [Apache-2.0](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/LICENSE) 라이선스로 제공됩니다. 이 라이선스는 별도로 운영되는 Genesis 서비스의 접근 권한을 부여하지 않습니다.

번들 구성 요소에는 각자의 라이선스가 적용됩니다. [NOTICE](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/NOTICE)와 [서드파티 고지](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/THIRD_PARTY_NOTICES.md)를 확인하세요.
