# Design Document: The "Elemental Catalyst" Expansion

## 1. The New Systems
To evolve the engine from a basic chase-and-fetch game into a deep roguelike, we will introduce four interacting systems. The core philosophy is **Emergent Interaction**: mechanics should not exist in isolation, but instead act as catalysts for one another.

### A. Deterministic Procedural Generation (The Foundation)
Since `Math.random` is forbidden, we implement a **Linear Congruential Generator (LCG)**. 
*   **Mechanism:** A simple formula: $X_{n+1} = (aX_n + c) \pmod m$.
*   **Purpose:** The `scenario N` input will serve as the initial seed. This PRNG will drive map generation (room placement), item spawning, and enemy variety.
*   **Depth:** Instead of a static map, the game now has infinite replayability while remaining 100% testable.

### B. The Elemental & Environmental Layer
The grid is no longer just "Wall" and "Floor." We introduce **Cell States**.
*   **Elements:** Fire, Water, Oil.
*   **Interactions:**
    *   **Oil + Fire** $\rightarrow$ Creates a "Blaze" (high damage, spreads to adjacent cells).
    *   **Water + Fire** $\rightarrow$ Extinguishes fire, creates "Steam" (obscures vision/blocks movement).
    *   **Water + Oil** $\rightarrow$ Oil floats (remains on top, but cannot be ignited until "pushed" by a specific trigger).
*   **Depth:** The environment becomes a weapon. A player can lure an enemy into an oil slick and ignite it with a fire-based item.

### C. Status Afflictions & Synergy
Combat moves from "stat-trading" to "status-management."
*   **Conditions:** 
    *   `Burning`: Takes damage every turn; spreads fire to adjacent cells.
    *   `Frozen`: Cannot move for $X$ turns; takes double damage from "Blunt" attacks.
    *   `Poisoned`: Gradual HP decay; reduces attack power.
*   **Depth:** Equipment now interacts with statuses. A "Fire Sword" doesn't just add $+2$ attack; it applies the `Burning` status.

### D. Enemy Archetypes & Behavioral State Machines
The "Chase" AI is replaced by a **State-Based AI**.
*   **Archetypes:**
    *   *The Stalker:* Standard chase AI.
    *   *The Pyromaniac:* Avoids water; actively tries to push the player into "Blaze" cells.
    *   *The Guardian:* Stays within a 3-tile radius of a specific item/altar.
*   **States:** `IDLE` $\rightarrow$ `PATROL` $\rightarrow$ `HUNT` $\rightarrow$ `FLEE` (triggered when HP < 20%).
*   **Depth:** Enemies no longer just follow the player; they react to the environment and their own health, creating tactical puzzles.

---

## 2. Turn-by-Turn Interaction Flow
To maintain determinism, the turn order is strictly sequenced. Every "tick" follows this pipeline:

1.  **Player Input Phase:** 
    *   Player moves or quaffs. If moving into an element (e.g., Oil), the player is "Coated."
2.  **Status Tick Phase:** 
    *   All entities (Player/Enemies) process current status effects (e.g., `Burning` deals damage).
3.  **Environmental Propagation Phase:** 
    *   Fire spreads to adjacent "Oil" or "Burning" entities.
    *   Steam dissipates.
    *   *Determinism Note:* Cells are processed in a fixed order (top-left to bottom-right) to ensure consistent fire spread.
4.  **Enemy AI Phase:** 
    *   Enemies evaluate their state machine.
    *   Enemies move/attack based on their archetype and the current cell state.
5.  **Resource Decay Phase:** 
    *   Hunger/Light counters decrement.
6.  **State Resolution:** 
    *   Check for deaths (HP $\le 0$).
    *   Update the game state for the next turn.

---

## 3. Game State & Output Format
To maintain "Exact Line Output" grading, the output string is expanded. Each turn prints one line containing the full state.

**New State Variables:**
- `seed`: The LCG seed used for this run.
- `status_p`: Player status (e.g., `NONE`, `BURN`, `POIS`).
- `status_e`: Enemy status.
- `env_fire_count`: Number of cells currently on fire.
- `turn`: Total turns elapsed (distinct from `steps`).
- `hunger`: Current hunger level.

**New Output Schema (CSV Format):**
`x,y,steps,turn,enemy_x,enemy_y,p_hp,e_hp,gold,potions,descended,p_atk,def,seed,status_p,status_e,fire_cells,hunger`

Example line: 
`5,6,12,15,7,6,18,12,30,1,0,5,2,12345,BURN,NONE,4,95`

---

## 4. Determinism and Testing

### Ensuring Determinism
1.  **LCG implementation:** Instead of `Math.random()`, we use a function `nextRand()` that modifies a global `currentSeed` variable. 
    *   `nextRand() { currentSeed = (1103515245 * currentSeed + 12345) % 2**31; return currentSeed; }`
2.  **Fixed Iteration:** When processing the map for fire spread or enemy movement, we never use `Object.keys()` or `for...in` (which can be non-deterministic in some JS environments). We use standard `for(let i=0; i < length; i++)` loops over arrays.
3.  **Seed Mapping:** `node main.js --scenario 5` $\rightarrow$ `Seed = 5 * 1000`.

### Testing Emergent Interactions
To test the "Depth," we design scenarios specifically to trigger the interaction chains:

*   **Scenario "The Fire-Trap":**
    *   *Setup:* Player is placed near an Oil cell; an enemy is placed on the opposite side.
    *   *Goal:* Test if the player can use a Fire Potion to ignite the Oil, which then spreads to the Enemy, triggering the `Burning` status and forcing the Enemy into the `FLEE` state.
*   **Scenario "The Frozen Wall":**
    *   *Setup:* Enemy is `Frozen`.
    *   *Goal:* Verify that the enemy does not move for 3 turns and that the player's attack damage is exactly doubled during this window.
*   **Scenario "The Extinguisher":**
    *   *Setup:* A cell is `Blaze`; a Water Potion is used on it.
    *   *Goal:* Verify the cell state changes to `Steam` and the `env_fire_count` decrements.