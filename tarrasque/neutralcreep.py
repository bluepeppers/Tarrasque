from .properties import *
from .lanecreep import LaneCreep
from .entity import register_entity
import re

@register_entity('DT_DOTA_BaseNPC_Creep_Neutral')
class NeutralCreep(LaneCreep):
    name = Property("DT_BaseEntity", "m_nModelIndex")\
        .apply(StringTableTrans("modelprecache"))\
        .apply(FuncTrans(lambda n: n[0]))\
        .apply(FuncTrans(lambda n: re.findall('(?<=/)[a-z\_]+(?=\.mdl)', n)[0]))
