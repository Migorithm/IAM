from enum import IntEnum, Enum


class AccessPermission(IntEnum):
    DEFAULT = 0
    PATENT = 1
    ELEC = 2
    CLAIMS = 4
    LEGAL = 8
    CHEM = 16
    CONTRACT = 32
    ACADEMIC = 64
    STATUTE = 128
    GENERAL = 256
    DOCS = 512
    PDF = 1024
    PROJECT = 2048
    GPU = 4096
    GPU_FOR_DOC = 8192

    # use_patent:bool #특허쪽 번역 권한
    # use_elec:bool #전기전자분야 번역 권한
    # use_claims:bool #특허 청구항 번역 권한
    # use_legal:bool  #법률 번역 권한
    # use_chem:bool #화학 분야..
    # use_contract : bool #계약서 관련 번역 분야.
    # use_academic : bool #학술관련 분야
    # use_statute : bool #법률제정 관련 분야
    # use_general : bool #일반 번역
    # use_docx:bool #file format - docx으로 파일을 올릴수 있는가?
    # use_pdf:bool #file format - pdf 파일을 업로드 할수 있는가?
    # use_project:bool #intelliCat을 사용할 수 있는가? - deprecated
    # use_gpu:bool # gpu boost서버를 쓸 수 있는가?
    # use_gpu_for_doc:bool # gpu boost서버를 쓸 수 있는가?


class GroupPermission(IntEnum):  # TODO -> GroupManagementPermission
    DEFAULT = 1
    ADD_USER = 2
    REMOVE_USER = 4
    GRANT_ACCESS_PERMISSION = 8
    REVOKE_ACCESS_PERMISSION = 16
    ADMIN = 32


class PlatformPermission(IntEnum):
    DEFAULT = 0
    VIEW = 1
    EDIT = 2


class PlatformRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
