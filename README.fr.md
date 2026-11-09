<p align="center">
  <a href="https://usegenesis.vercel.app/"><img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle"></a>&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h1 align="center">Aidez votre agent à comprendre les changements de code.</h1>

<p align="center">
  <a href="https://usegenesis.vercel.app/">Site web</a> &nbsp;·&nbsp;
  <a href="#genesis-get-started"><strong>Commencer</strong></a> &nbsp;·&nbsp;
  <a href="#genesis-docs">Documentation</a> &nbsp;·&nbsp;
  <a href="#genesis-stars">Historique des étoiles</a>
</p>

<p align="center"><a href="README.md">English</a> &nbsp;·&nbsp; <a href="README.zh-CN.md">简体中文</a> &nbsp;·&nbsp; <a href="README.ja.md">日本語</a> &nbsp;·&nbsp; <a href="README.ko.md">한국어</a> &nbsp;·&nbsp; <a href="README.de.md">Deutsch</a> &nbsp;·&nbsp; <strong>Français</strong> &nbsp;·&nbsp; <a href="README.es.md">Español</a></p>

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
      <img src="assets/readme/code-intelligence-animation.gif" alt="Illustration du processus de revue : une modification de code Python passe par l’analyse du contexte, du comportement et des risques pour aboutir à un rapport de revue." width="100%">
    </picture>
  </a>
</p>

<p align="center"><sub><a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md">Illustration du processus de revue</a></sub></p>

<a id="genesis-get-started"></a>

## Commencer dans votre agent de développement

La CLI et l'analyse statique sont open source. La revue sémantique utilise le
service hébergé de Genesis. Le code source n'est envoyé qu'avec votre accord.

### 1. Installer une seule fois

Collez cette demande dans Codex ou Claude Code, dans le projet à examiner :

```text
Configure Genesis depuis https://github.com/GenesisAgentInfra/genesis-cli.
Lis son README et docs/coding-agents.md. Installe la CLI en dehors de ce
projet et le skill genesis-review pour mon agent actuel au niveau utilisateur.
Réutilise une installation existante si possible. Vérifie la version de la CLI
et l'installation du skill. Effectue uniquement la configuration ; ne lance
pas encore de revue et n'envoie aucun code.
```

L'environnement d'exécution de votre agent doit disposer d'un accès au shell,
de Git, de Python 3.12+ et d'uv 0.13.7. Les paquets s'installent depuis les sources
et ne sont pas encore disponibles sur PyPI.
[Configuration à distance ou dans le cloud et détection du skill](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md#maintenance-and-troubleshooting).

<details>
<summary>Installation manuelle</summary>

Exécutez ces commandes en dehors de l'application à examiner :

```sh
git clone https://github.com/GenesisAgentInfra/genesis-cli.git
cd genesis-cli
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis version
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent codex
uv run --package genesis-ci --no-dev --frozen genesis agent status --agent codex
```

Utilisez `--agent claude` pour Claude Code ou `--agent both`. L'installation se
fait par défaut au niveau utilisateur. Le programme d'installation préserve les
instructions de l'agent, les autorisations et les identifiants existants, ainsi
que tout skill déjà présent qui diffère de celui à installer.

[Options de configuration et dépannage](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md).

</details>

### 2. Demander une revue

Si le skill n'est pas visible, ouvrez une nouvelle session de l'agent, puis
formulez cette demande :

```text
Utilise Genesis pour examiner mes modifications non committées.
Explique ce qui change pour les utilisateurs, les principaux risques et ce
qui reste à tester. Montre-moi les extraits de code source qui seront
transmis avant de les envoyer.
```

Vous pouvez aussi sélectionner le skill explicitement :

| Agent | Invocation |
| --- | --- |
| Codex | `$genesis-review` suivi de votre demande |
| Claude Code | `/genesis-review` suivi de votre demande |

Précisez une comparaison de branches ou une paire de commits pour examiner un
autre périmètre. Les descriptions de tâches et les schémas de flux constituent
un contexte facultatif.

L'essai partagé officiel fonctionne sans `genesis auth` lorsqu'aucun paramètre
de connexion personnel n'est configuré. Il utilise un quota limité commun à
tous les utilisateurs. Aucune clé API de fournisseur de modèles n'est requise.
[Accès et limites de l'essai](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md#default-shared-trial).

## Ce que couvre votre revue

| Domaine | Ce que vous obtenez |
| --- | --- |
| Comportement métier | Des éléments avant/après montrant comment le comportement de l'application peut changer. |
| Chemins affectés | Les appelants et les chemins de code liés à la modification, ainsi que les éventuels schémas de flux fournis. |
| Coûts, attente et échecs | Des risques conditionnels et des estimations statiques, lorsque les éléments disponibles permettent de les étayer. |
| Tests | Ce que vérifie le code source des tests associés et les assertions qui peuvent manquer. |
| Vérification | Des contrôles suggérés et les points qui nécessitent encore des éléments probants. |

Genesis analyse le code source Python sans exécuter votre application ni ses
tests. Les exigences manquantes et les comportements non élucidés restent
explicitement signalés comme des lacunes dans la revue.

## De votre modification au rapport

1. **Préparer localement.** Genesis capture les modifications choisies et en
   extrait les éléments probants. Votre agent présente les extraits de code
   source et les faits sélectionnés pour l'envoi.
2. **Autoriser l'envoi.** Avec votre accord, Genesis transmet ces éléments à son
   service hébergé. Vous pouvez aussi conserver l'analyse en local et obtenir
   un rapport partiel.
3. **Lire les résultats dans le chat.** Votre agent explique le rapport, vérifie
   les éléments probants et son statut, puis indique ce qui reste à vérifier.

Les rapports sont enregistrés dans `.genesis/analyses/<run-id>/`, au sein de
votre projet :

- `summary.md` : commencez par le résumé lisible.
- `report.md` : examinez les résultats détaillés, les éléments probants et les statuts.
- `report.json` : utilisez le résultat structuré dans vos propres outils.

Codes de sortie : **0** signifie que l'analyse est terminée dans le périmètre
déclaré ; **2** indique un rapport partiel exploitable ; **1** signifie que le
résultat demandé n'a pas pu être produit. Excluez `.genesis/` de Git : ce dossier
peut contenir du code source capturé.

## Code source et service

Le dépôt public contient la CLI et l'analyse statique. L'équipe Genesis exploite
le service sémantique privé ; son implémentation serveur n'est pas incluse pour
un auto-hébergement.

L'aperçu et l'analyse hors ligne restent locaux. Installer le skill n'active pas
de revue automatique après chaque modification.

[Traitement des données, clés personnelles et configuration](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md).

<a id="genesis-docs"></a>

## Documentation

- [Guide des agents de développement](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md) : configuration, détection du skill, instructions d'équipe et dépannage.
- [Guide de la CLI](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md) : commandes, contexte facultatif, identifiants et traitement des données.
- [GitHub Action](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/github-action.md) : configuration de l'automatisation du dépôt ; l'analyse hébergée nécessite une clé Genesis fournie explicitement.
- [Contribuer](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/CONTRIBUTING.md) : développer et tester le client.
- [Périmètre du dépôt](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/repository-boundary.md) et [schémas des rapports](https://github.com/GenesisAgentInfra/code-intelligence-protocol).

<a id="genesis-stars"></a>

## Historique des étoiles

<a href="https://www.star-history.com/#GenesisAgentInfra/genesis-cli&amp;Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date&amp;theme=dark">
    <img src="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date" alt="Historique des étoiles de GenesisAgentInfra/genesis-cli" width="100%">
  </picture>
</a>

[Voir sur Star History](https://www.star-history.com/#GenesisAgentInfra/genesis-cli&Date)


## Licence

Le code original de Genesis CLI est sous licence [Apache-2.0](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/LICENSE).
Cette licence ne donne pas accès au service Genesis, exploité séparément.
Les composants inclus conservent leurs propres licences ; consultez [NOTICE](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/NOTICE)
et les [mentions relatives aux composants tiers](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/THIRD_PARTY_NOTICES.md).
