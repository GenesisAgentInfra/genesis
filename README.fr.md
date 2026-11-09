<p align="center">
  <a href="https://usegenesis.vercel.app/"><img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle"></a>&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h1 align="center">Des garde-fous pour chaque modification de votre agent.</h1>

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

## Pourquoi utiliser Genesis ?

Voyez comment une modification du code affecte le résultat livré à vos utilisateurs.

| Impact pour l’utilisateur | Ce que Genesis vous aide à examiner |
| --- | --- |
| **L’agent continue de travailler. Le résultat n’arrive jamais.** [Source](https://github.com/openai/openai-agents-python/issues/191) | Les changements des conditions de fin et d’arrêt. |
| **L’utilisateur dit non. L’action s’exécute quand même.** [Source](https://github.com/langchain-ai/langchain/issues/40492) | Les changements des contrôles d’approbation et des chemins d’exécution. |
| **Une demande. La même action se produit deux fois.** [Source](https://github.com/langchain-ai/langgraph/issues/9185) | Les chemins de reprise et les contrôles contre les actions en double. |
| **La même tâche consomme plus de tokens.** [Source](https://github.com/microsoft/agent-framework/issues/5049) | La croissance des prompts et les appels supplémentaires au modèle. |
| **La tâche se termine. Vos utilisateurs attendent plus longtemps.** [Source](https://github.com/openai/openai-agents-python/issues/2386) | Les appels bloquants et les étapes séquentielles. |

<a id="genesis-get-started"></a>

## Commencer dans votre agent de développement

La CLI et l'analyse statique sont open source. La revue sémantique utilise le
service hébergé de Genesis. Le code source n'est envoyé qu'avec votre accord.

### 1. Installer une seule fois

Collez cette demande dans Codex ou Claude Code, dans le projet à examiner :

```text
Configure Genesis depuis https://github.com/GenesisAgentInfra/genesis-cli.
Lis le README et docs/coding-agents.md. Installe la CLI hors de ce projet et le
skill genesis-review au niveau utilisateur pour mon agent actuel. Réutilise
l'installation existante et actualise si nécessaire un skill géré non modifié.
Suis "Configure CR preparation in this project" dans docs/coding-agents.md :
ajoute aux instructions de ce projet la revue Genesis avant de préparer une CR/PR,
en conservant le contenu existant. Vérifie la CLI, le skill et la règle ; indique le fichier modifié.
Configure uniquement : aucune analyse ni aucun envoi de code maintenant.
Les futurs envois nécessitent une autorisation couvrant le service et les sources sélectionnées.
```

**Après configuration :** demandez « Prépare ces changements pour une revue de code ». Les instructions du projet
prévoient une revue Genesis et une explication du résultat avant de finaliser la description de la CR/PR, sans GitHub CI.
C'est une consigne pour l'agent, pas une garantie d'exécution, un hook Git ou un blocage de fusion. Le skill est installé
au niveau utilisateur ; cette règle s'applique au projet actuel. Installer la CLI seule ne l'ajoute pas.
[Configuration manuelle, mise à jour et suppression](docs/coding-agents.md#configure-cr-preparation-in-this-project).

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

</details>

### 2. Demander une revue

```text
Prépare ces changements pour une revue de code (CR/PR), en suivant la consigne Genesis du projet.
Explique les résultats et les points non vérifiés avant de finaliser la description. Montre le périmètre de l'envoi avant tout transfert.
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
