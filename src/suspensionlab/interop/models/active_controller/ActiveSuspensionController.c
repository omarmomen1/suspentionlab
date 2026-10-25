/*
 * ActiveSuspensionController.c
 * =============================
 * SuspensionLab PRO — Phase 7.6 Genuine Feedback Co-Simulation
 * Dynamic Actuator / Feedback Controller FMU (FMI 2.0 Co-Simulation)
 *
 * Control Law:
 *   F_cmd = -c_sky * v_s - k_p * (z_s - z_u) - c_rel * (v_s - v_u)
 *   F_sat = clip(F_cmd, -f_max, +f_max)
 *
 * Actuator Lag Dynamics (optional delay_s > 0):
 *   delay_s * d(F_act)/dt = F_sat - F_act
 *   If delay_s <= 0: F_act = F_sat
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "fmi2Functions.h"

#define MODEL_IDENTIFIER "ActiveSuspensionController"
#define MODEL_GUID "{b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e}"

#define VR_C_SKY        1
#define VR_K_P          2
#define VR_C_REL        3
#define VR_F_MAX        4
#define VR_DELAY_S      5

#define VR_Z_S          10
#define VR_V_S          11
#define VR_Z_U          12
#define VR_V_U          13
#define VR_SUSP_TRAVEL  14

#define VR_F_ACT        20
#define VR_F_CMD        21
#define VR_IS_SATURATED 22
#define VR_TIME         23

typedef enum {
    MODEL_STATE_INSTANTIATED,
    MODEL_STATE_INITIALIZATION_MODE,
    MODEL_STATE_STEP_MODE,
    MODEL_STATE_TERMINATED,
    MODEL_STATE_ERROR
} ModelState;

typedef struct {
    /* Parameters */
    fmi2Real c_sky;
    fmi2Real k_p;
    fmi2Real c_rel;
    fmi2Real f_max;
    fmi2Real delay_s;

    /* Inputs */
    fmi2Real z_s;
    fmi2Real v_s;
    fmi2Real z_u;
    fmi2Real v_u;
    fmi2Real susp_travel;

    /* Internal State */
    fmi2Real f_act_state;

    /* Outputs */
    fmi2Real f_act;
    fmi2Real f_cmd;
    fmi2Real is_saturated;

    /* Simulation Clock & State */
    fmi2Real time;
    ModelState state;
    char instanceName[128];
    const fmi2CallbackFunctions* callbacks;
    fmi2Boolean loggingOn;
} ActiveControllerInstance;

static void compute_control(ActiveControllerInstance* comp) {
    fmi2Real stroke = comp->susp_travel;
    fmi2Real rel_vel = comp->v_s - comp->v_u;
    fmi2Real f_sat;

    /* If susp_travel was not explicitly set, compute from z_s - z_u */
    if (fabs(stroke) < 1e-12 && (fabs(comp->z_s) > 1e-12 || fabs(comp->z_u) > 1e-12)) {
        stroke = comp->z_s - comp->z_u;
    }

    comp->f_cmd = -comp->c_sky * comp->v_s - comp->k_p * stroke - comp->c_rel * rel_vel;

    /* Saturation limits */
    if (comp->f_max > 0.0) {
        if (comp->f_cmd > comp->f_max) {
            f_sat = comp->f_max;
            comp->is_saturated = 1.0;
        } else if (comp->f_cmd < -comp->f_max) {
            f_sat = -comp->f_max;
            comp->is_saturated = 1.0;
        } else {
            f_sat = comp->f_cmd;
            comp->is_saturated = 0.0;
        }
    } else {
        f_sat = comp->f_cmd;
        comp->is_saturated = 0.0;
    }

    if (comp->delay_s <= 1e-6) {
        comp->f_act = f_sat;
        comp->f_act_state = f_sat;
    } else {
        comp->f_act = comp->f_act_state;
    }
}

static void step_actuator_filter(ActiveControllerInstance* comp, fmi2Real h) {
    fmi2Real stroke = comp->susp_travel;
    fmi2Real rel_vel = comp->v_s - comp->v_u;
    fmi2Real f_cmd;
    fmi2Real f_sat;

    if (fabs(stroke) < 1e-12 && (fabs(comp->z_s) > 1e-12 || fabs(comp->z_u) > 1e-12)) {
        stroke = comp->z_s - comp->z_u;
    }

    f_cmd = -comp->c_sky * comp->v_s - comp->k_p * stroke - comp->c_rel * rel_vel;
    comp->f_cmd = f_cmd;

    if (comp->f_max > 0.0) {
        if (f_cmd > comp->f_max) {
            f_sat = comp->f_max;
            comp->is_saturated = 1.0;
        } else if (f_cmd < -comp->f_max) {
            f_sat = -comp->f_max;
            comp->is_saturated = 1.0;
        } else {
            f_sat = f_cmd;
            comp->is_saturated = 0.0;
        }
    } else {
        f_sat = f_cmd;
        comp->is_saturated = 0.0;
    }

    if (comp->delay_s <= 1e-6) {
        comp->f_act = f_sat;
        comp->f_act_state = f_sat;
    } else {
        /* Exact analytical exponential integration for 1st-order lag */
        fmi2Real alpha = exp(-h / comp->delay_s);
        comp->f_act_state = comp->f_act_state * alpha + f_sat * (1.0 - alpha);
        comp->f_act = comp->f_act_state;
    }
}

/* FMI 2.0 Functions */

FMI2_Export const char* fmi2GetTypesPlatform(void) {
    return fmi2TypesPlatform;
}

FMI2_Export const char* fmi2GetVersion(void) {
    return fmi2Version;
}

FMI2_Export fmi2Status fmi2SetDebugLogging(fmi2Component c, fmi2Boolean loggingOn,
                                          size_t nCategories, const fmi2String categories[]) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    (void)nCategories; (void)categories;
    if (!comp) return fmi2Fatal;
    comp->loggingOn = loggingOn;
    return fmi2OK;
}

FMI2_Export fmi2Component fmi2Instantiate(fmi2String instanceName, fmi2Type fmuType,
                                         fmi2String fmuGUID, fmi2String fmuResourceLocation,
                                         const fmi2CallbackFunctions* functions,
                                         fmi2Boolean visible, fmi2Boolean loggingOn) {
    ActiveControllerInstance* comp;
    (void)fmuType; (void)fmuResourceLocation; (void)visible;

    if (!functions || !functions->allocateMemory || !functions->freeMemory) {
        return NULL;
    }

    if (strcmp(fmuGUID, MODEL_GUID) != 0) {
        return NULL;
    }

    comp = (ActiveControllerInstance*)functions->allocateMemory(1, sizeof(ActiveControllerInstance));
    if (!comp) return NULL;
    memset(comp, 0, sizeof(ActiveControllerInstance));

    /* Default parameters: skyhook damping = 2000 Ns/m */
    comp->c_sky = 2000.0;
    comp->k_p = 0.0;
    comp->c_rel = 0.0;
    comp->f_max = 5000.0;
    comp->delay_s = 0.0;

    /* Inputs */
    comp->z_s = 0.0;
    comp->v_s = 0.0;
    comp->z_u = 0.0;
    comp->v_u = 0.0;
    comp->susp_travel = 0.0;

    /* Internal State */
    comp->f_act_state = 0.0;

    comp->time = 0.0;
    comp->state = MODEL_STATE_INSTANTIATED;
    strncpy(comp->instanceName, instanceName ? instanceName : "ActiveSuspensionController", sizeof(comp->instanceName) - 1);
    comp->callbacks = functions;
    comp->loggingOn = loggingOn;

    compute_control(comp);
    return (fmi2Component)comp;
}

FMI2_Export void fmi2FreeInstance(fmi2Component c) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    if (comp && comp->callbacks && comp->callbacks->freeMemory) {
        comp->callbacks->freeMemory(comp);
    }
}

FMI2_Export fmi2Status fmi2SetupExperiment(fmi2Component c, fmi2Boolean toleranceDefined,
                                          fmi2Real tolerance, fmi2Real startTime,
                                          fmi2Boolean stopTimeDefined, fmi2Real stopTime) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    (void)toleranceDefined; (void)tolerance; (void)stopTimeDefined; (void)stopTime;
    if (!comp) return fmi2Fatal;
    comp->time = startTime;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2EnterInitializationMode(fmi2Component c) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->state = MODEL_STATE_INITIALIZATION_MODE;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2ExitInitializationMode(fmi2Component c) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->state = MODEL_STATE_STEP_MODE;
    compute_control(comp);
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2Terminate(fmi2Component c) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->state = MODEL_STATE_TERMINATED;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2Reset(fmi2Component c) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->z_s = 0.0;
    comp->v_s = 0.0;
    comp->z_u = 0.0;
    comp->v_u = 0.0;
    comp->susp_travel = 0.0;
    comp->f_act_state = 0.0;
    comp->time = 0.0;
    comp->state = MODEL_STATE_INSTANTIATED;
    compute_control(comp);
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2GetReal(fmi2Component c, const fmi2ValueReference vr[],
                                  size_t nvr, fmi2Real value[]) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    size_t i;
    if (!comp || !vr || !value) return fmi2Fatal;

    for (i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_C_SKY:        value[i] = comp->c_sky; break;
            case VR_K_P:          value[i] = comp->k_p; break;
            case VR_C_REL:        value[i] = comp->c_rel; break;
            case VR_F_MAX:        value[i] = comp->f_max; break;
            case VR_DELAY_S:      value[i] = comp->delay_s; break;
            case VR_Z_S:          value[i] = comp->z_s; break;
            case VR_V_S:          value[i] = comp->v_s; break;
            case VR_Z_U:          value[i] = comp->z_u; break;
            case VR_V_U:          value[i] = comp->v_u; break;
            case VR_SUSP_TRAVEL:  value[i] = comp->susp_travel; break;
            case VR_F_ACT:        value[i] = comp->f_act; break;
            case VR_F_CMD:        value[i] = comp->f_cmd; break;
            case VR_IS_SATURATED: value[i] = comp->is_saturated; break;
            case VR_TIME:         value[i] = comp->time; break;
            default:
                return fmi2Error;
        }
    }
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[],
                                  size_t nvr, const fmi2Real value[]) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    size_t i;
    if (!comp || !vr || !value) return fmi2Fatal;

    for (i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_C_SKY:       comp->c_sky = value[i]; break;
            case VR_K_P:         comp->k_p = value[i]; break;
            case VR_C_REL:       comp->c_rel = value[i]; break;
            case VR_F_MAX:       comp->f_max = value[i]; break;
            case VR_DELAY_S:     comp->delay_s = value[i]; break;
            case VR_Z_S:         comp->z_s = value[i]; break;
            case VR_V_S:         comp->v_s = value[i]; break;
            case VR_Z_U:         comp->z_u = value[i]; break;
            case VR_V_U:         comp->v_u = value[i]; break;
            case VR_SUSP_TRAVEL: comp->susp_travel = value[i]; break;
            case VR_F_ACT:       comp->f_act = value[i]; comp->f_act_state = value[i]; break;
            default:
                return fmi2Error;
        }
    }
    compute_control(comp);
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2GetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Integer value[]) {
    (void)c; (void)vr; (void)nvr; (void)value;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2SetInteger(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Integer value[]) {
    (void)c; (void)vr; (void)nvr; (void)value;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2GetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Boolean value[]) {
    (void)c; (void)vr; (void)nvr; (void)value;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2SetBoolean(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Boolean value[]) {
    (void)c; (void)vr; (void)nvr; (void)value;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2GetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2String value[]) {
    (void)c; (void)vr; (void)nvr; (void)value;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2SetString(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2String value[]) {
    (void)c; (void)vr; (void)nvr; (void)value;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2DoStep(fmi2Component c, fmi2Real currentCommunicationPoint,
                                  fmi2Real communicationStepSize, fmi2Boolean noSetFMUStatePriorToCurrentPoint) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    (void)noSetFMUStatePriorToCurrentPoint;

    if (!comp) return fmi2Fatal;
    if (comp->state != MODEL_STATE_STEP_MODE) return fmi2Error;
    if (communicationStepSize <= 0.0) return fmi2Error;

    comp->time = currentCommunicationPoint;
    step_actuator_filter(comp, communicationStepSize);
    comp->time = currentCommunicationPoint + communicationStepSize;

    return fmi2OK;
}

FMI2_Export fmi2Status fmi2CancelStep(fmi2Component c) {
    (void)c;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2GetStatus(fmi2Component c, const fmi2StatusKind s, fmi2Status* value) {
    (void)c; (void)s;
    if (value) *value = fmi2OK;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2GetRealStatus(fmi2Component c, const fmi2StatusKind s, fmi2Real* value) {
    ActiveControllerInstance* comp = (ActiveControllerInstance*)c;
    if (!comp || !value) return fmi2Fatal;
    if (s == fmi2LastSuccessfulTime) {
        *value = comp->time;
        return fmi2OK;
    }
    return fmi2Discard;
}

FMI2_Export fmi2Status fmi2GetIntegerStatus(fmi2Component c, const fmi2StatusKind s, fmi2Integer* value) {
    (void)c; (void)s; (void)value;
    return fmi2Discard;
}

FMI2_Export fmi2Status fmi2GetBooleanStatus(fmi2Component c, const fmi2StatusKind s, fmi2Boolean* value) {
    (void)c; (void)s; (void)value;
    return fmi2Discard;
}

FMI2_Export fmi2Status fmi2GetStringStatus(fmi2Component c, const fmi2StatusKind s, fmi2String* value) {
    (void)c; (void)s; (void)value;
    return fmi2Discard;
}

FMI2_Export fmi2Status fmi2SetRealInputDerivatives(fmi2Component c, const fmi2ValueReference vr[], size_t nvr,
                                                   const fmi2Integer order[], const fmi2Real value[]) {
    (void)c; (void)vr; (void)nvr; (void)order; (void)value;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2GetRealOutputDerivatives(fmi2Component c, const fmi2ValueReference vr[], size_t nvr,
                                                    const fmi2Integer order[], fmi2Real value[]) {
    (void)c; (void)vr; (void)nvr; (void)order; (void)value;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2SetFMUstate(fmi2Component c, fmi2FMUstate s) {
    (void)c; (void)s;
    return fmi2Discard;
}

FMI2_Export fmi2Status fmi2GetFMUstate(fmi2Component c, fmi2FMUstate* s) {
    (void)c; (void)s;
    return fmi2Discard;
}

FMI2_Export fmi2Status fmi2FreeFMUstate(fmi2Component c, fmi2FMUstate* s) {
    (void)c; (void)s;
    return fmi2Discard;
}

FMI2_Export fmi2Status fmi2SerializedFMUstateSize(fmi2Component c, fmi2FMUstate s, size_t* size) {
    (void)c; (void)s; (void)size;
    return fmi2Discard;
}

FMI2_Export fmi2Status fmi2SerializeFMUstate(fmi2Component c, fmi2FMUstate s, fmi2Byte serializedState[], size_t size) {
    (void)c; (void)s; (void)serializedState; (void)size;
    return fmi2Discard;
}

FMI2_Export fmi2Status fmi2DeSerializeFMUstate(fmi2Component c, const fmi2Byte serializedState[], size_t size, fmi2FMUstate* s) {
    (void)c; (void)serializedState; (void)size; (void)s;
    return fmi2Discard;
}

FMI2_Export fmi2Status fmi2GetDirectionalDerivative(fmi2Component c,
                                                   const fmi2ValueReference vUnknown_ref[], size_t nUnknown,
                                                   const fmi2ValueReference vKnown_ref[], size_t nKnown,
                                                   const fmi2Real dvKnown[], fmi2Real dvUnknown[]) {
    (void)c; (void)vUnknown_ref; (void)nUnknown; (void)vKnown_ref; (void)nKnown; (void)dvKnown; (void)dvUnknown;
    return fmi2Discard;
}
