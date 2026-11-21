import json, os, shutil, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


class FakeEnv:
    """With FakeEnv() as e: the fake gh first on PATH, FAKE_GH_DIR and REA_BOARD_CONFIG in a temp folder; all undone on exit."""

    KEYS = ("PATH", "FAKE_GH_DIR", "REA_BOARD_CONFIG")

    def __init__(self, config=None):
        self.config = config or {}

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in self.KEYS}
        self.root = tempfile.mkdtemp(prefix="rea-board-fakes-")
        self.gh = self.root + "/gh"
        os.mkdir(self.gh)
        self.cfg = self.root + "/config.json"
        self.write_config(self.config)
        os.environ.update(PATH=HERE + os.pathsep + self.saved["PATH"], FAKE_GH_DIR=self.gh, REA_BOARD_CONFIG=self.cfg)
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    def write_config(self, cfg):
        with open(self.cfg, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)

    def gh_fixture(self, name, **fx):
        with open("%s/%s.json" % (self.gh, name), "w", encoding="utf-8") as fh:
            json.dump(fx, fh)

    def gh_calls(self):
        p = self.gh + "/calls.log"
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh.read().splitlines()]
