# Third-party notices

Original Genesis source uses Apache-2.0. Dependencies keep their own licenses;
Apache-2.0 does not relicense third-party code. The lockfiles (`uv.lock`,
`viewer/package-lock.json`) record exact versions.

## Bundled in the viewer page

`genesis map render` writes a page built from `viewer/`. The built file,
`packages/genesis_ci/src/genesis_ci/assets/viewer/index.html`, ships in the
`genesis-ci` wheel and contains code from these packages:

| Package | License |
| --- | --- |
| react, react-dom | MIT |
| @xyflow/react | MIT |
| radix-ui | MIT |
| commit-graph | MIT |
| clsx | MIT |
| tailwind-merge | MIT |
| tailwindcss | MIT |
| tw-animate-css | MIT |
| class-variance-authority | Apache-2.0 |
| lucide-react | ISC |
