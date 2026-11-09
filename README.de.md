<p align="center">
  <a href="https://usegenesis.vercel.app/"><img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle"></a>&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h1 align="center">Damit dein Coding-Agent Codeänderungen versteht.</h1>

<p align="center">
  <a href="https://usegenesis.vercel.app/">Website</a> &nbsp;·&nbsp;
  <a href="#genesis-get-started"><strong>Erste Schritte</strong></a> &nbsp;·&nbsp;
  <a href="#genesis-docs">Dokumentation</a> &nbsp;·&nbsp;
  <a href="#genesis-stars">Star-Verlauf</a>
</p>

<p align="center"><a href="README.md">English</a> &nbsp;·&nbsp; <a href="README.zh-CN.md">简体中文</a> &nbsp;·&nbsp; <a href="README.ja.md">日本語</a> &nbsp;·&nbsp; <a href="README.ko.md">한국어</a> &nbsp;·&nbsp; <strong>Deutsch</strong> &nbsp;·&nbsp; <a href="README.fr.md">Français</a> &nbsp;·&nbsp; <a href="README.es.md">Español</a></p>

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
      <img src="assets/readme/code-intelligence-animation.gif" alt="Veranschaulichter Review-Ablauf: Eine Python-Codeänderung wird im Kontext sowie auf Verhalten und Risiken analysiert und in einem Review-Bericht zusammengefasst." width="100%">
    </picture>
  </a>
</p>

<p align="center"><sub><a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md">Der Review-Ablauf im Überblick</a></sub></p>

<a id="genesis-get-started"></a>

## Mit deinem Coding-Agent starten

Die CLI und die statische Analyse sind Open Source. Für das semantische Review
wird der gehostete Genesis-Dienst verwendet. Quellcode wird erst nach deiner
Zustimmung übertragen.

### 1. Einmal installieren

Füge diese Anfrage in Codex oder Claude Code im zu prüfenden Projekt ein:

```text
Richte Genesis von https://github.com/GenesisAgentInfra/genesis-cli ein.
Lies README und docs/coding-agents.md. Installiere die CLI außerhalb dieses Projekts
und den genesis-review-Skill für meinen aktuellen Agenten auf Benutzerebene.
Verwende eine vorhandene Installation und aktualisiere bei Bedarf einen unveränderten verwalteten Skill.
Befolge "Configure CR preparation in this project" in docs/coding-agents.md:
Ergänze die Projektanweisungen um eine Genesis-Prüfung vor der CR/PR-Vorbereitung,
ohne bestehende Inhalte zu ersetzen. Prüfe CLI, Skill und Regel und nenne die geänderte Datei.
Jetzt nur einrichten, keinen Code prüfen oder hochladen. Künftige Uploads benötigen
weiterhin eine Genehmigung für den Zieldienst und die ausgewählten Quellen.
```

**Nach der Einrichtung:** Bitten Sie den Agenten, Änderungen für ein Code-Review vorzubereiten. Die Projektanweisung
sieht vor, zuerst Genesis auszuführen und das Ergebnis zu erklären, bevor die CR/PR-Beschreibung fertiggestellt wird.
GitHub CI ist dafür nicht nötig. Dies ist eine Agentenanweisung, keine Ausführungsgarantie, kein Git-Hook und keine
Merge-Sperre. Der Skill gilt auf Benutzerebene, die Regel für dieses Projekt. Die CLI-Installation allein ergänzt sie nicht.
[Manuelle Einrichtung, Aktualisierung und Entfernung](docs/coding-agents.md#configure-cr-preparation-in-this-project).

In der Ausführungsumgebung deines Agents werden Shell-Zugriff, Git, Python 3.12+
und uv 0.13.7 benötigt. Die Pakete werden aus dem Quellcode installiert und sind
noch nicht auf PyPI verfügbar.
[Remote-/Cloud-Einrichtung und Skill-Erkennung](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md#maintenance-and-troubleshooting).

<details>
<summary>Manuelle Installation</summary>

Führe diese Befehle außerhalb der Anwendung aus, die du prüfen möchtest:

```sh
git clone https://github.com/GenesisAgentInfra/genesis-cli.git
cd genesis-cli
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis version
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent codex
uv run --package genesis-ci --no-dev --frozen genesis agent status --agent codex
```

Verwende `--agent claude` für Claude Code oder `--agent both`. Standardmäßig
erfolgt die Installation auf Benutzerebene. Das Installationsprogramm behält
bestehende Agent-Anweisungen, Berechtigungen, Zugangsdaten und einen bereits
vorhandenen, abweichenden Skill bei.

[Einrichtungsoptionen und Fehlerbehebung](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md).

</details>

### 2. Ein Review anfordern

Starte eine neue Agent-Sitzung, falls der Skill nicht sichtbar ist. Stelle dann
diese Anfrage:

```text
Bereite diese Änderungen für ein Code-Review (CR/PR) gemäß der Genesis-Anweisung dieses Projekts vor.
Erkläre Ergebnisse und offene Prüfpunkte vor der fertigen Beschreibung. Zeige vor dem Hochladen den Umfang der Übertragung.
```

Du kannst den Skill auch ausdrücklich auswählen:

| Agent | Aufruf |
| --- | --- |
| Codex | `$genesis-review`, gefolgt von deiner Anfrage |
| Claude Code | `/genesis-review`, gefolgt von deiner Anfrage |

Gib einen Branch-Vergleich oder ein Commit-Paar an, wenn du einen anderen Umfang
prüfen möchtest. Aufgabenbeschreibungen und Ablaufdiagramme sind optionaler
Kontext.

Der offizielle gemeinsame Testzugang funktioniert ohne `genesis auth`, sofern
keine persönlichen Verbindungseinstellungen konfiguriert sind. Er nutzt ein
begrenztes Kontingent, das sich alle Nutzer teilen. Ein API-Schlüssel eines
Modellanbieters ist nicht erforderlich.
[Zugang und Grenzen des Testzugangs](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md#default-shared-trial).

## Was dein Review abdeckt

| Bereich | Ergebnis |
| --- | --- |
| Fachliches Verhalten | Vorher-/Nachher-Belege dafür, wie sich das Verhalten der Anwendung ändern kann. |
| Betroffene Pfade | Aufrufer und Codepfade, die mit der Änderung zusammenhängen, sowie gegebenenfalls bereitgestellte Ablaufdiagramme. |
| Kosten, Wartezeiten und Fehler | Bedingte Risiken und statische Schätzungen, soweit die verfügbaren Belege sie stützen. |
| Tests | Was der zugehörige Testquellcode prüft und welche Assertions möglicherweise fehlen. |
| Verifikation | Vorschläge für Prüfungen und Lücken, für die noch Belege fehlen. |

Genesis analysiert Python-Quellcode, ohne deine Anwendung oder ihre Tests
auszuführen. Fehlende Anforderungen und ungeklärtes Verhalten bleiben im Review
als Lücken ausgewiesen.

## Von deiner Änderung zum Bericht

1. **Lokal vorbereiten.** Genesis erfasst die ausgewählten Änderungen und
   extrahiert Codebelege. Dein Agent zeigt die Quellcodeausschnitte und Fakten,
   die für die Übertragung ausgewählt wurden.
2. **Übertragung freigeben.** Mit deiner Zustimmung sendet Genesis dieses
   Material an seinen gehosteten Dienst. Du kannst die Analyse auch lokal
   belassen und stattdessen einen Teilbericht erhalten.
3. **Ergebnisse im Chat lesen.** Dein Agent erklärt den Bericht, prüft seine
   Belege und seinen Status und benennt, was noch verifiziert werden muss.

Die Berichte werden in `.genesis/analyses/<run-id>/` in deinem Projekt gespeichert:

- `summary.md`: Beginne mit der lesbaren Zusammenfassung.
- `report.md`: Prüfe die detaillierten Ergebnisse, Belege und Statusangaben.
- `report.json`: Verwende das strukturierte Ergebnis in deinen eigenen Tools.

Exit-Codes: **0** bedeutet abgeschlossen innerhalb des angegebenen Umfangs,
**2** steht für einen nutzbaren Teilbericht und **1** bedeutet, dass das
angeforderte Ergebnis nicht erzeugt werden konnte. Nimm `.genesis/` nicht in Git
auf; das Verzeichnis kann erfassten Quellcode enthalten.

## Quellcode und Dienst

Das öffentliche Repository enthält die CLI und die statische Analyse. Das
Genesis-Team betreibt den privaten semantischen Dienst; dessen Serverimplementierung
ist nicht für den Eigenbetrieb enthalten.

Vorschau und Offline-Analyse bleiben lokal. Die Installation des Skills aktiviert
keine automatischen Reviews nach jeder Änderung.

[Datenverarbeitung, persönliche Schlüssel und Konfiguration](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md).

<a id="genesis-docs"></a>

## Dokumentation

- [Leitfaden für Coding-Agents](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md): Einrichtung, Skill-Erkennung, Team-Anweisungen und Fehlerbehebung.
- [CLI-Leitfaden](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md): Befehle, optionaler Kontext, Zugangsdaten und Datenverarbeitung.
- [GitHub Action](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/github-action.md): Repository-Automatisierung einrichten; die gehostete Analyse erfordert einen explizit angegebenen Genesis-Schlüssel.
- [Mitwirken](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/CONTRIBUTING.md): Den Client entwickeln und testen.
- [Repository-Abgrenzung](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/repository-boundary.md) und [Berichtsschemas](https://github.com/GenesisAgentInfra/code-intelligence-protocol).

<a id="genesis-stars"></a>

## Star-Verlauf

<a href="https://www.star-history.com/#GenesisAgentInfra/genesis-cli&amp;Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date&amp;theme=dark">
    <img src="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date" alt="Star-Verlauf von GenesisAgentInfra/genesis-cli" width="100%">
  </picture>
</a>

[Auf Star History ansehen](https://www.star-history.com/#GenesisAgentInfra/genesis-cli&Date)


## Lizenz

Der ursprüngliche Genesis-CLI-Code steht unter der [Apache-2.0-Lizenz](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/LICENSE).
Diese Lizenz gewährt keinen Zugang zum separat betriebenen Genesis-Dienst.
Mitgelieferte Komponenten behalten ihre jeweiligen Lizenzen; siehe [NOTICE](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/NOTICE)
und [Drittanbieterhinweise](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/THIRD_PARTY_NOTICES.md).
