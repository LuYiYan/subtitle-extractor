# -*- coding: utf-8 -*-
"""Keep QPT from dropping paddleocr while it packages paddlex.

QPT 1.0b8 treats both ``paddleocr`` and ``paddlex`` as
``AddPaddlePaddlePackage`` and stores each first-run installer under
``opt/<module name>/``. The class name is the module name, so the second
package overwrites the first. v1.4.3 kept paddlex and never installed
paddleocr, which is the ``No module named 'paddleocr'`` error when
「硬字幕转繁体」 starts OCR.
"""


def paddle_module_name(package_name):
    """Return a QPT module directory name that is unique per distribution."""
    package_name = (package_name or "paddle").replace("-", "_")
    return "AddPaddlePaddlePackage_" + package_name


def apply_unique_qpt_paddle_module_names():
    """Give each Paddle family package its own first-run install folder.

    paddlepaddle itself stays on QPT's normal special-case path. This only
    stops paddleocr and paddlex from sharing one serialized install command.
    Dependencies still come from the frozen requirements file.
    """
    from qpt.modules.base import GENERAL_LEVEL_REDUCE
    from qpt.modules.package import CustomPackage
    from qpt.modules import paddle_family

    def init(self, name=None, version=None, deploy_mode=None):
        package_name = name or "paddle"
        CustomPackage.__init__(
            self,
            package_name,
            version=version,
            deploy_mode=deploy_mode,
            no_dependent=True,
            name=paddle_module_name(package_name),
        )
        self.level = GENERAL_LEVEL_REDUCE - 0.1

    paddle_family.AddPaddlePaddlePackage.__init__ = init
