#ifndef FMI2_TYPES_PLATFORM_H
#define FMI2_TYPES_PLATFORM_H

/*
 * Standard FMI 2.0 Types Platform definition
 */

#define fmi2TypesPlatform "default"

typedef void*           fmi2Component;
typedef void*           fmi2ComponentEnvironment;
typedef void*           fmi2FMUstate;
typedef unsigned int    fmi2ValueReference;
typedef double          fmi2Real;
typedef int             fmi2Integer;
typedef int             fmi2Boolean;
typedef char            fmi2Char;
typedef const fmi2Char* fmi2String;
typedef char            fmi2Byte;

#define fmi2True  1
#define fmi2False 0

#endif /* FMI2_TYPES_PLATFORM_H */
