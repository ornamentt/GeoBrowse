#

# a session of one task running

__all__ = [
    "AgentSession",
]

from .utils import get_unique_id

class AgentSession:
    """
    Session owns the image registry (code-side source of truth).
    The agent/LLM should only reference image IDs like `img:0`, `img:1`, ...
    """
    def __init__(self, id=None, task="", image=None, **kwargs):
        self.id = id if id is not None else get_unique_id("S")
        self.info = {}
        self.info.update(kwargs)
        self.task = task  # target task
        self.image = image  # input image
        self.steps = []  # a list of dicts to indicate each step's running, simply use dict to max flexibility
        # -------------------------
        # Image Registry (code-side)
        # -------------------------
        # images: { "img:0": {"url": "...", "desc": "...", "w":..., "h":..., "mime":..., "source":...}, ... }
        self.registry = {
            "images": {},
            "next_img_id": 0,
        }
        self.input_image_id = None

    def to_dict(self):
        return self.__dict__.copy()

    def from_dict(self, data: dict):
        for k, v in data.items():
            assert k in self.__dict__
            self.__dict__[k] = v
        if not isinstance(getattr(self, "registry", None), dict):
            self.registry = {"images": {}, "next_img_id": 0}
        if self.registry.get("images") == {} and self.registry.get("next_img_id", 0) == 0:
            if isinstance(getattr(self, "image", None), str) and self.image.strip():
                self.input_image_id = self.register_image(
                    url=self.image,
                    desc="original_input",
                    meta={"source": "user_input"}
                )

    @classmethod
    def init_from_dict(cls, data: dict):
        ret = cls()
        ret.from_dict(data)
        return ret

    @classmethod
    def init_from_data(cls, task, image, steps=(), **kwargs):
        ret = cls(task=task, image=image, **kwargs)  # 让 __init__ 去注册
        ret.steps.extend(steps)
        return ret

    def num_of_steps(self):
        return len(self.steps)

    def get_current_step(self):
        return self.get_specific_step(idx=-1)

    def get_specific_step(self, idx: int):
        return self.steps[idx]

    def get_latest_steps(self, count=0, include_last=False):
        if count <= 0:
            ret = self.steps if include_last else self.steps[:-1]
        else:
            ret = self.steps[-count:] if include_last else self.steps[-count-1:-1]
        return ret

    def add_step(self, step_info):
        self.steps.append(step_info)

    # ---------- registry API (core) ----------
    def _alloc_image_id(self) -> str:
        rid = f"img:{self.registry['next_img_id']}"
        self.registry["next_img_id"] += 1
        return rid

    def register_image(self, url: str, desc: str, meta: dict) -> str:
        """
        Register a real, tool-usable image URL and return a stable image_id (img:N).
        """
        if not isinstance(url, str) or not url.strip():
            raise ValueError("register_image: url must be a non-empty string")

        rid = self._alloc_image_id()
        item = {
            "url": url,
            "desc": desc or "",
            "meta": meta or None,
        }
        self.registry["images"][rid] = item
        return rid

    def has_image(self, image_id: str) -> bool:
        return image_id in self.registry["images"]

    def resolve_image(self, image_id: str) -> dict | None:
        """
        Return registry entry for image_id, or None if not found.
        """
        return self.registry["images"].get(image_id)

    def get_image_url(self, image_id: str) -> str:
        """
        Resolve image_id to a real URL. Raise a structured error for upstream handling.
        """
        item = self.resolve_image(image_id)
        if not item:
            raise ValueError(f"IMAGE_ID_NOT_FOUND: {image_id}")
        return item["url"]

    def list_images(self):
        """
        Lightweight summary for prompts/UI/debug.
        """
        out = []
        for k, v in self.registry["images"].items():
            out.append({
                "id": k,
                "desc": v.get("desc", ""),
                "w": v.get("w"),
                "h": v.get("h"),
                "mime": v.get("mime"),
                "source": v.get("source"),
            })
        return out
