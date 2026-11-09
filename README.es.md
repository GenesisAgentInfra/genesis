<p align="center">
  <a href="https://usegenesis.vercel.app/"><img src="assets/readme/favicon.svg" alt="Genesis icon" width="52" height="52" align="middle"></a>&nbsp;&nbsp;
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/wordmark-dark.svg">
    <img src="assets/readme/wordmark-light.svg" alt="Genesis" width="240" align="middle">
  </picture>
</p>

<h1 align="center">Salvaguardas para cada cambio en tu agente.</h1>

<p align="center">
  <a href="https://usegenesis.vercel.app/">Sitio web</a> &nbsp;·&nbsp;
  <a href="#genesis-get-started"><strong>Primeros pasos</strong></a> &nbsp;·&nbsp;
  <a href="#genesis-docs">Documentación</a> &nbsp;·&nbsp;
  <a href="#genesis-stars">Historial de estrellas</a>
</p>

<p align="center"><a href="README.md">English</a> &nbsp;·&nbsp; <a href="README.zh-CN.md">简体中文</a> &nbsp;·&nbsp; <a href="README.ja.md">日本語</a> &nbsp;·&nbsp; <a href="README.ko.md">한국어</a> &nbsp;·&nbsp; <a href="README.de.md">Deutsch</a> &nbsp;·&nbsp; <a href="README.fr.md">Français</a> &nbsp;·&nbsp; <strong>Español</strong></p>

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
      <img src="assets/readme/code-intelligence-animation.gif" alt="Ilustración del proceso de revisión: un cambio en código Python pasa por el análisis del contexto, el comportamiento y los riesgos hasta generar un informe de revisión." width="100%">
    </picture>
  </a>
</p>

<p align="center"><sub><a href="https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md">Ilustración del proceso de revisión</a></sub></p>

<a id="genesis-get-started"></a>

## Empieza desde tu agente de programación

La CLI y el análisis estático son de código abierto. La revisión semántica usa
el servicio alojado de Genesis, con tu aprobación antes de enviar código fuente.

### 1. Instala una sola vez

Pega esta solicitud en Codex o Claude Code dentro del proyecto que quieras revisar:

```text
Configura Genesis desde https://github.com/GenesisAgentInfra/genesis-cli.
Lee el README y docs/coding-agents.md. Instala la CLI fuera de este proyecto y el
skill genesis-review para mi agente actual con alcance de usuario. Reutiliza la
instalación existente y actualiza, si hace falta, un skill administrado sin modificaciones.
Sigue "Configure CR preparation in this project" en docs/coding-agents.md:
añade a las instrucciones de este proyecto la revisión con Genesis antes de preparar una CR/PR,
preservando el contenido existente. Verifica CLI, skill y regla; indica qué archivo cambió.
Por ahora solo configura: no analices ni subas código. Los envíos futuros requieren
autorización que cubra el servicio de destino y las fuentes seleccionadas.
```

**Después de configurar:** pide al agente « Prepara estos cambios para revisión de código ». Las instrucciones del proyecto
le indican que ejecute Genesis y explique el resultado antes de finalizar la descripción de la CR/PR. No requiere GitHub CI.
Es una instrucción para el agente, no una garantía de ejecución, un hook de Git ni un bloqueo de merge. El skill se instala
para el usuario; esta regla se aplica al proyecto actual. Instalar solo la CLI no añade la regla.
[Configuración manual, actualización y eliminación](docs/coding-agents.md#configure-cr-preparation-in-this-project).

El entorno donde se ejecute tu agente debe tener acceso al shell, Git,
Python 3.12+ y uv 0.13.7. Los paquetes se instalan desde el código fuente y aún
no están disponibles en PyPI.
[Configuración remota o en la nube y detección del skill](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md#maintenance-and-troubleshooting).

<details>
<summary>Instalación manual</summary>

Ejecuta estos comandos fuera de la aplicación que quieras revisar:

```sh
git clone https://github.com/GenesisAgentInfra/genesis-cli.git
cd genesis-cli
uv sync --python 3.12 --package genesis-ci --no-dev --frozen
uv run --package genesis-ci --no-dev --frozen genesis version
uv run --package genesis-ci --no-dev --frozen genesis agent install --agent codex
uv run --package genesis-ci --no-dev --frozen genesis agent status --agent codex
```

Usa `--agent claude` para Claude Code o `--agent both`. El alcance predeterminado
es el de usuario. El instalador conserva las instrucciones del agente, los
permisos y las credenciales existentes, así como cualquier skill ya instalado
que difiera del que se va a instalar.

[Opciones de configuración y solución de problemas](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md).

</details>

### 2. Solicita una revisión

Si el skill no aparece, inicia una nueva sesión del agente y haz esta solicitud:

```text
Prepara estos cambios para revisión de código (CR/PR), siguiendo la instrucción de Genesis de este proyecto.
Explica los hallazgos y lo que falta verificar antes de finalizar la descripción. Muestra el alcance de la subida antes de enviar.
```

También puedes seleccionar el skill de forma explícita:

| Agente | Invocación |
| --- | --- |
| Codex | `$genesis-review` seguido de tu solicitud |
| Claude Code | `/genesis-review` seguido de tu solicitud |

Indica una comparación de ramas o un par de commits si quieres revisar otro
alcance. Las descripciones de tareas y los mapas de flujo son contexto opcional.

La prueba compartida oficial funciona sin `genesis auth` cuando no hay ajustes
de conexión personales configurados. Usa una cuota limitada compartida por
todos los usuarios. No requiere una clave API de un proveedor de modelos.
[Acceso y límites de la prueba](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md#default-shared-trial).

## Qué cubre tu revisión

| Área | Qué obtienes |
| --- | --- |
| Comportamiento de negocio | Evidencia del antes y el después que muestra cómo puede cambiar el comportamiento de la aplicación. |
| Rutas afectadas | Los puntos de llamada y las rutas de código relacionados con el cambio, junto con los mapas de flujo que se hayan proporcionado. |
| Coste, espera y fallos | Riesgos condicionales y estimaciones estáticas cuando la evidencia disponible los respalda. |
| Pruebas | Qué comprueba el código fuente de las pruebas relacionadas y qué aserciones podrían faltar. |
| Verificación | Comprobaciones sugeridas y aspectos que aún necesitan evidencia. |

Genesis analiza el código fuente Python sin ejecutar tu aplicación ni sus
pruebas. Los requisitos ausentes y los comportamientos sin resolver quedan
señalados explícitamente como lagunas en la revisión.

## De tu cambio al informe

1. **Prepara en local.** Genesis captura los cambios elegidos y extrae evidencia
   del código. Tu agente muestra los fragmentos de código fuente y los hechos
   seleccionados para el envío.
2. **Aprueba el envío.** Con tu autorización, Genesis envía ese material a su
   servicio alojado. También puedes mantener el análisis en local y recibir
   un informe parcial.
3. **Lee los resultados en el chat.** Tu agente explica el informe, comprueba
   su evidencia y su estado, e identifica qué falta por verificar.

Los informes se guardan en `.genesis/analyses/<run-id>/`, dentro de tu proyecto:

- `summary.md`: empieza por el resumen legible.
- `report.md`: examina los resultados detallados, la evidencia y los estados.
- `report.json`: usa el resultado estructurado en tus propias herramientas.

Códigos de salida: **0** significa que el análisis se completó dentro del alcance
declarado; **2** indica un informe parcial utilizable; **1** significa que no se
pudo producir el resultado solicitado. Excluye `.genesis/` de Git: puede contener
código fuente capturado.

## Código fuente y servicio

El repositorio público contiene la CLI y el análisis estático. El equipo de
Genesis opera el servicio semántico privado; su implementación de servidor no
se incluye para alojarla por tu cuenta.

La vista previa y el análisis sin conexión se realizan en local. Instalar el
skill no activa revisiones automáticas después de cada edición.

[Tratamiento de datos, claves personales y configuración](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md).

<a id="genesis-docs"></a>

## Documentación

- [Guía para agentes de programación](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/coding-agents.md): configuración, detección del skill, instrucciones de equipo y solución de problemas.
- [Guía de la CLI](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/usage.md): comandos, contexto opcional, credenciales y tratamiento de datos.
- [GitHub Action](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/github-action.md): configura la automatización del repositorio; el análisis alojado requiere una clave Genesis proporcionada explícitamente.
- [Contribuir](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/CONTRIBUTING.md): desarrolla y prueba el cliente.
- [Límites del repositorio](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/docs/repository-boundary.md) y [esquemas de los informes](https://github.com/GenesisAgentInfra/code-intelligence-protocol).

<a id="genesis-stars"></a>

## Historial de estrellas

<a href="https://www.star-history.com/#GenesisAgentInfra/genesis-cli&amp;Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date&amp;theme=dark">
    <img src="https://api.star-history.com/svg?repos=GenesisAgentInfra/genesis-cli&amp;type=Date" alt="Historial de estrellas de GenesisAgentInfra/genesis-cli" width="100%">
  </picture>
</a>

[Ver en Star History](https://www.star-history.com/#GenesisAgentInfra/genesis-cli&Date)


## Licencia

El código original de Genesis CLI se distribuye bajo la licencia [Apache-2.0](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/LICENSE).
Esta licencia no concede acceso al servicio Genesis, que se opera por separado.
Los componentes incluidos conservan sus propias licencias; consulta [NOTICE](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/NOTICE)
y los [avisos de terceros](https://github.com/GenesisAgentInfra/genesis-cli/blob/main/THIRD_PARTY_NOTICES.md).
