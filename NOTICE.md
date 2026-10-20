# Origin and compatibility

Not yet dead is the public, portable distribution of the **ninnin 0.3.0**
agent handoff skill. The original skill declares the MIT license.

This distribution keeps `ninnin_core`, the `urn:ninnin:handoff:v1` schema
identity, the existing v1 bundle layout, generated handoff headings and the
`scripts/ninnin.py` entry point for compatibility. The public skill name is
`not-yet-dead`; its preferred entry point is `scripts/not_yet_dead.py`.

The standalone source is drawn from the existing CLI, handoff, workspace,
resume and Store modules. Inherited behavioral tests are adapted to use the
operating system temporary directory and the public script path. Public
documentation and sample data are written for this distribution.

The related collaboration workbench, its model workers, host-specific session
APIs and private project records are outside this distribution.

Installing or cloning this public project does not rename an existing local
`ninnin` installation. Choose the destination explicitly when installing.
