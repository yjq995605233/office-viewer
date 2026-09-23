# Office / 01

Interactive office reconstruction viewer: scene overview, first-person walking, and inspection of 20 semantic assets.

## Controls

- Drag to orbit; scroll to zoom.
- Choose a view preset or select an object from the list.
- Click Enter walkthrough: WASD / arrow keys to move, mouse to look, R to reset, Escape to exit.
- View the source panorama with the image button.

Desktop Chrome or Edge is recommended for keyboard/mouse walking. Touch devices support the observation view.

## Data

This is a research visualization with inferred geometry and nominal scale, not a measured digital survey. The scene comes from export run `20260911T032046192242Z`.

This repository contains the built website and display assets. It does not contain the original Blender project or reconstruction pipeline. Access to this public repository does not grant a separate license to reuse the scene data or source image.

The viewer uses three.js 0.186.0. See THIRD_PARTY_NOTICES.txt for its MIT license.

## Hosting

GitHub Pages publishes from the root of the main branch. All model, image, script and stylesheet references are relative so the viewer also works under the repository URL path.