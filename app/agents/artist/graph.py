from app.core.state import GlobalState

# TODO: Replace stub with real image generation (e.g. Stable Diffusion / DALL-E).
# This node runs in parallel with weapon_designer (same superstep via forge_fork fan-out).
# It writes `generated_icon` to state; handlers.py applies it to the final weapon payload.


class ArtistAgent:
    async def generate_icon_node(self, state: GlobalState) -> dict:
        concept = state.get("design_concept") or {}
        codename = concept.get("codename", "unknown")
        print(f"[Artist] (stub) Generating icon for: {codename} → weapon_axe.png")
        return {"generated_icon": "weapon_axe.png"}


artist_agent = ArtistAgent()
