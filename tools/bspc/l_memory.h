// bspc build shim: idlib's l_memory.h is disabled (the game's botlib
// allocates through its import table); bspc and the AAS code it links use
// bspc's l_mem.c
#ifndef GetMemory
void *GetMemory(unsigned long size);
void *GetClearedMemory(unsigned long size);
void FreeMemory(void *ptr);
#endif
#define GetHunkMemory(size)			GetMemory(size)
#define GetClearedHunkMemory(size)	GetClearedMemory(size)
