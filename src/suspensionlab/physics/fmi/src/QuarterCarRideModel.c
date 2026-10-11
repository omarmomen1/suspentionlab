/*
 * QuarterCarRideModel.c
 * =====================
 * SuspensionLab PRO — FMI 2.0 Co-Simulation Implementation
 * 2-DOF Quarter Car Multibody Dynamics Engine
 *
 * Implements standard FMI 2.0 C functions for co-simulation.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "fmi2Functions.h"

#define MODEL_IDENTIFIER "QuarterCarRideModel"
#define MODEL_GUID "{8c3f4e21-9a7b-4d61-b531-ec72f0941ab2}"

/* Value References matching modelDescription.xml */
#define VR_M_S                1
#define VR_M_U                2
#define VR_K_S                3
#define VR_C                  4
#define VR_K_T                5
#define VR_MR                 6
#define VR_C_T                7

#define VR_Z_ROAD             10
#define VR_DZ_ROAD            11

#define VR_Z_S                20
#define VR_Z_U                21
#define VR_SUSP_TRAVEL        22
#define VR_TIRE_LOAD_DYNAMIC  23
#define VR_BODY_ACCEL         24
#define VR_TIME               25

typedef enum {
    MODEL_STATE_INSTANTIATED,
    MODEL_STATE_INITIALIZATION_MODE,
    MODEL_STATE_STEP_MODE,
    MODEL_STATE_TERMINATED,
    MODEL_STATE_ERROR
} ModelState;

typedef struct {
    /* Parameters */
    fmi2Real m_s;
    fmi2Real m_u;
    fmi2Real k_s;
    fmi2Real c;
    fmi2Real k_t;
    fmi2Real MR;
    fmi2Real c_t;

    /* Inputs */
    fmi2Real z_road;
    fmi2Real dz_road;

    /* States: x = [z_s, dz_s, z_u, dz_u] */
    fmi2Real x[4];

    /* Outputs */
    fmi2Real z_s;
    fmi2Real z_u;
    fmi2Real susp_travel;
    fmi2Real tire_load_dynamic;
    fmi2Real body_accel;
    fmi2Real time;

    /* Simulation Control */
    fmi2Real startTime;
    fmi2Real stopTime;
    fmi2Boolean stopTimeDefined;

    ModelState state;
    char instanceName[256];
    fmi2CallbackFunctions callbacks;
    fmi2Boolean loggingOn;
} QuarterCarModelInstance;

static void update_outputs(QuarterCarModelInstance* comp) {
    fmi2Real k_w = comp->k_s * (comp->MR * comp->MR);
    fmi2Real c_w = comp->c * (comp->MR * comp->MR);
    fmi2Real v_susp = comp->x[1] - comp->x[3];
    fmi2Real z_susp = comp->x[0] - comp->x[2];

    fmi2Real F_damper_w = c_w * v_susp;
    fmi2Real F_spring_w = k_w * z_susp;

    comp->z_s = comp->x[0];
    comp->z_u = comp->x[2];
    comp->susp_travel = z_susp;
    comp->body_accel = (-F_damper_w - F_spring_w) / comp->m_s;
    /* Dynamic tire load variation = k_t * (z_u - z_road) + c_t * (dz_u - dz_road) */
    comp->tire_load_dynamic = comp->k_t * (comp->x[2] - comp->z_road) + comp->c_t * (comp->x[3] - comp->dz_road);
}

static void eval_derivs(const fmi2Real x[4], fmi2Real z_road, fmi2Real dz_road,
                        const QuarterCarModelInstance* comp, fmi2Real dxdt[4]) {
    fmi2Real k_w = comp->k_s * (comp->MR * comp->MR);
    fmi2Real c_w = comp->c * (comp->MR * comp->MR);
    fmi2Real z_s = x[0];
    fmi2Real dz_s = x[1];
    fmi2Real z_u = x[2];
    fmi2Real dz_u = x[3];

    fmi2Real v_susp = dz_s - dz_u;
    fmi2Real z_susp = z_s - z_u;

    fmi2Real F_damper_w = c_w * v_susp;
    fmi2Real F_spring_w = k_w * z_susp;

    /* Sprung acceleration */
    fmi2Real ddz_s = (-F_damper_w - F_spring_w) / comp->m_s;

    /* Tire vertical force on unsprung mass */
    fmi2Real F_tire = comp->k_t * (z_road - z_u) + comp->c_t * (dz_road - dz_u);

    /* Unsprung acceleration */
    fmi2Real ddz_u = (F_damper_w + F_spring_w + F_tire) / comp->m_u;

    dxdt[0] = dz_s;
    dxdt[1] = ddz_s;
    dxdt[2] = dz_u;
    dxdt[3] = ddz_u;
}

/* Runge-Kutta 4 Integrator */
static void rk4_step(QuarterCarModelInstance* comp, fmi2Real dt) {
    fmi2Real k1[4], k2[4], k3[4], k4[4];
    fmi2Real x_temp[4];
    int i;

    eval_derivs(comp->x, comp->z_road, comp->dz_road, comp, k1);

    for (i = 0; i < 4; i++) x_temp[i] = comp->x[i] + 0.5 * dt * k1[i];
    eval_derivs(x_temp, comp->z_road, comp->dz_road, comp, k2);

    for (i = 0; i < 4; i++) x_temp[i] = comp->x[i] + 0.5 * dt * k2[i];
    eval_derivs(x_temp, comp->z_road, comp->dz_road, comp, k3);

    for (i = 0; i < 4; i++) x_temp[i] = comp->x[i] + dt * k3[i];
    eval_derivs(x_temp, comp->z_road, comp->dz_road, comp, k4);

    for (i = 0; i < 4; i++) {
        comp->x[i] += (dt / 6.0) * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]);
    }
}

/* =========================================================================
 * FMI 2.0 Standard API Implementation
 * ========================================================================= */

FMI2_Export const char* fmi2GetTypesPlatform(void) {
    return fmi2TypesPlatform;
}

FMI2_Export const char* fmi2GetVersion(void) {
    return "2.0";
}

FMI2_Export fmi2Status fmi2SetDebugLogging(fmi2Component c, fmi2Boolean loggingOn,
                                          size_t nCategories, const fmi2String categories[]) {
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->loggingOn = loggingOn;
    return fmi2OK;
}

FMI2_Export fmi2Component fmi2Instantiate(fmi2String instanceName, fmi2Type fmuType, fmi2String fmuGUID,
                                          fmi2String fmuResourceLocation, const fmi2CallbackFunctions* functions,
                                          fmi2Boolean visible, fmi2Boolean loggingOn) {
    QuarterCarModelInstance* comp;
    (void)fmuResourceLocation;
    (void)visible;

    if (fmuType != fmi2CoSimulation) {
        return NULL;
    }
    if (!fmuGUID || strcmp(fmuGUID, MODEL_GUID) != 0) {
        return NULL;
    }

    if (functions && functions->allocateMemory) {
        comp = (QuarterCarModelInstance*)functions->allocateMemory(1, sizeof(QuarterCarModelInstance));
    } else {
        comp = (QuarterCarModelInstance*)calloc(1, sizeof(QuarterCarModelInstance));
    }

    if (!comp) return NULL;

    if (functions) {
        comp->callbacks = *functions;
    }
    if (instanceName) {
        strncpy(comp->instanceName, instanceName, sizeof(comp->instanceName) - 1);
    }
    comp->loggingOn = loggingOn;

    /* Canonical Quarter Car default parameters */
    comp->m_s = 300.0;
    comp->m_u = 35.0;
    comp->k_s = 25000.0;
    comp->c = 2050.0;
    comp->k_t = 200000.0;
    comp->MR = 0.85;
    comp->c_t = 0.0;

    comp->z_road = 0.0;
    comp->dz_road = 0.0;
    comp->time = 0.0;

    memset(comp->x, 0, sizeof(comp->x));
    update_outputs(comp);

    comp->state = MODEL_STATE_INSTANTIATED;
    return (fmi2Component)comp;
}

FMI2_Export void fmi2FreeInstance(fmi2Component c) {
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
    if (!comp) return;

    if (comp->callbacks.freeMemory) {
        comp->callbacks.freeMemory(comp);
    } else {
        free(comp);
    }
}

FMI2_Export fmi2Status fmi2SetupExperiment(fmi2Component c, fmi2Boolean toleranceDefined, fmi2Real tolerance,
                                           fmi2Real startTime, fmi2Boolean stopTimeDefined, fmi2Real stopTime) {
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
    (void)toleranceDefined;
    (void)tolerance;
    if (!comp) return fmi2Fatal;

    comp->startTime = startTime;
    comp->time = startTime;
    comp->stopTimeDefined = stopTimeDefined;
    comp->stopTime = stopTime;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2EnterInitializationMode(fmi2Component c) {
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->state = MODEL_STATE_INITIALIZATION_MODE;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2ExitInitializationMode(fmi2Component c) {
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
    if (!comp) return fmi2Fatal;

    update_outputs(comp);
    comp->state = MODEL_STATE_STEP_MODE;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2Terminate(fmi2Component c) {
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->state = MODEL_STATE_TERMINATED;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2Reset(fmi2Component c) {
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
    if (!comp) return fmi2Fatal;

    memset(comp->x, 0, sizeof(comp->x));
    comp->time = comp->startTime;
    comp->z_road = 0.0;
    comp->dz_road = 0.0;
    update_outputs(comp);
    comp->state = MODEL_STATE_INSTANTIATED;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2GetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, fmi2Real value[]) {
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
    size_t i;
    if (!comp) return fmi2Fatal;

    for (i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_M_S:                value[i] = comp->m_s; break;
            case VR_M_U:                value[i] = comp->m_u; break;
            case VR_K_S:                value[i] = comp->k_s; break;
            case VR_C:                  value[i] = comp->c; break;
            case VR_K_T:                value[i] = comp->k_t; break;
            case VR_MR:                 value[i] = comp->MR; break;
            case VR_C_T:                value[i] = comp->c_t; break;
            case VR_Z_ROAD:             value[i] = comp->z_road; break;
            case VR_DZ_ROAD:            value[i] = comp->dz_road; break;
            case VR_Z_S:                value[i] = comp->z_s; break;
            case VR_Z_U:                value[i] = comp->z_u; break;
            case VR_SUSP_TRAVEL:        value[i] = comp->susp_travel; break;
            case VR_TIRE_LOAD_DYNAMIC:  value[i] = comp->tire_load_dynamic; break;
            case VR_BODY_ACCEL:         value[i] = comp->body_accel; break;
            case VR_TIME:               value[i] = comp->time; break;
            default:
                return fmi2Error;
        }
    }
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[], size_t nvr, const fmi2Real value[]) {
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
    size_t i;
    if (!comp) return fmi2Fatal;

    for (i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_M_S:
                if (value[i] <= 0.0) return fmi2Error;
                comp->m_s = value[i];
                break;
            case VR_M_U:
                if (value[i] <= 0.0) return fmi2Error;
                comp->m_u = value[i];
                break;
            case VR_K_S:
                if (value[i] < 0.0) return fmi2Error;
                comp->k_s = value[i];
                break;
            case VR_C:
                if (value[i] < 0.0) return fmi2Error;
                comp->c = value[i];
                break;
            case VR_K_T:
                if (value[i] < 0.0) return fmi2Error;
                comp->k_t = value[i];
                break;
            case VR_MR:
                if (value[i] <= 0.0 || value[i] > 2.0) return fmi2Error;
                comp->MR = value[i];
                break;
            case VR_C_T:
                if (value[i] < 0.0) return fmi2Error;
                comp->c_t = value[i];
                break;
            case VR_Z_ROAD:
                comp->z_road = value[i];
                break;
            case VR_DZ_ROAD:
                comp->dz_road = value[i];
                break;
            default:
                return fmi2Error;
        }
    }
    update_outputs(comp);
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
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
    fmi2Real remaining_h;
    fmi2Real dt_sub;
    (void)noSetFMUStatePriorToCurrentPoint;

    if (!comp) return fmi2Fatal;
    if (comp->state != MODEL_STATE_STEP_MODE) return fmi2Error;
    if (communicationStepSize <= 0.0) return fmi2Error;

    comp->time = currentCommunicationPoint;
    remaining_h = communicationStepSize;

    /* Sub-stepping loop for numerical precision (max dt = 0.5 ms) */
    while (remaining_h > 1e-12) {
        dt_sub = remaining_h > 0.0005 ? 0.0005 : remaining_h;
        rk4_step(comp, dt_sub);
        remaining_h -= dt_sub;
    }

    comp->time = currentCommunicationPoint + communicationStepSize;
    update_outputs(comp);

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
    QuarterCarModelInstance* comp = (QuarterCarModelInstance*)c;
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

FMI2_Export fmi2Status fmi2GetFMUstate(fmi2Component c, fmi2FMUstate* s) {
    (void)c; (void)s;
    return fmi2Error;
}

FMI2_Export fmi2Status fmi2SetFMUstate(fmi2Component c, fmi2FMUstate s) {
    (void)c; (void)s;
    return fmi2Error;
}

FMI2_Export fmi2Status fmi2FreeFMUstate(fmi2Component c, fmi2FMUstate* s) {
    (void)c; (void)s;
    return fmi2Error;
}

FMI2_Export fmi2Status fmi2SerializedFMUstateSize(fmi2Component c, fmi2FMUstate s, size_t* size) {
    (void)c; (void)s; (void)size;
    return fmi2Error;
}

FMI2_Export fmi2Status fmi2SerializeFMUstate(fmi2Component c, fmi2FMUstate s, fmi2Byte data[], size_t size) {
    (void)c; (void)s; (void)data; (void)size;
    return fmi2Error;
}

FMI2_Export fmi2Status fmi2DeSerializeFMUstate(fmi2Component c, const fmi2Byte data[], size_t size, fmi2FMUstate* s) {
    (void)c; (void)data; (void)size; (void)s;
    return fmi2Error;
}

FMI2_Export fmi2Status fmi2GetDirectionalDerivative(fmi2Component c, const fmi2ValueReference vUnknown_ref[], size_t nUnknown,
                                                    const fmi2ValueReference vKnown_ref[], size_t nKnown,
                                                    const fmi2Real dvKnown[], fmi2Real dvUnknown[]) {
    (void)c; (void)vUnknown_ref; (void)nUnknown; (void)vKnown_ref; (void)nKnown; (void)dvKnown; (void)dvUnknown;
    return fmi2Error;
}
