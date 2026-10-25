/*
 * ActiveQuarterCarModel.c
 * =======================
 * SuspensionLab PRO — Phase 7.6 Genuine Feedback Co-Simulation
 * 2-DOF Active Quarter-Car Suspension Plant FMU (FMI 2.0 Co-Simulation)
 *
 * Governing Equations:
 *   m_s * ddz_s = -k_s * (z_s - z_u) - c_s * (dz_s - dz_u) + F_act
 *   m_u * ddz_u = +k_s * (z_s - z_u) + c_s * (dz_s - dz_u) - k_t * (z_u - z_r) - c_t * (dz_u - dz_r) - F_act
 *
 * Positive Force Convention:
 *   F_act > 0 pushes sprung mass UPWARDS (+z_s) and unsprung mass DOWNWARDS (-z_u).
 *   Action-reaction pairs strictly satisfy Newton's Third Law: (+F_act) + (-F_act) = 0.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "fmi2Functions.h"

#define MODEL_IDENTIFIER "ActiveQuarterCarModel"
#define MODEL_GUID "{a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d}"

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
#define VR_F_ACT              12

#define VR_Z_S                20
#define VR_V_S                21
#define VR_Z_U                22
#define VR_V_U                23
#define VR_SUSP_TRAVEL        24
#define VR_TIRE_LOAD_DYNAMIC  25
#define VR_BODY_ACCEL         26
#define VR_POWER_ACT          27
#define VR_TIME               28

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
    fmi2Real f_act;

    /* States: x = [z_s, v_s, z_u, v_u] */
    fmi2Real z_s;
    fmi2Real v_s;
    fmi2Real z_u;
    fmi2Real v_u;

    /* Outputs */
    fmi2Real susp_travel;
    fmi2Real tire_load_dynamic;
    fmi2Real body_accel;
    fmi2Real power_act;

    /* Simulation Clock & State */
    fmi2Real time;
    ModelState state;
    char instanceName[128];
    const fmi2CallbackFunctions* callbacks;
    fmi2Boolean loggingOn;
} ActiveQuarterCarInstance;

static void compute_derivatives(ActiveQuarterCarInstance* comp,
                                const fmi2Real x[4],
                                fmi2Real dxdt[4],
                                fmi2Real* out_ddz_s) {
    fmi2Real zs = x[0];
    fmi2Real vs = x[1];
    fmi2Real zu = x[2];
    fmi2Real vu = x[3];

    fmi2Real kw = comp->k_s * (comp->MR * comp->MR);
    fmi2Real cw = comp->c * (comp->MR * comp->MR);

    /* Suspension force between body and wheel assembly */
    fmi2Real f_spring = kw * (zs - zu);
    fmi2Real f_damper = cw * (vs - vu);
    fmi2Real f_susp_passive = f_spring + f_damper;

    /* Tire contact force */
    fmi2Real f_tire = comp->k_t * (zu - comp->z_road) + comp->c_t * (vu - comp->dz_road);

    /* Sprung mass acceleration: m_s * ddz_s = -f_susp_passive + f_act */
    fmi2Real ddz_s = (-f_susp_passive + comp->f_act) / comp->m_s;

    /* Unsprung mass acceleration: m_u * ddz_u = +f_susp_passive - f_tire - f_act */
    fmi2Real ddz_u = (f_susp_passive - f_tire - comp->f_act) / comp->m_u;

    dxdt[0] = vs;
    dxdt[1] = ddz_s;
    dxdt[2] = vu;
    dxdt[3] = ddz_u;

    if (out_ddz_s) {
        *out_ddz_s = ddz_s;
    }
}

static void update_outputs(ActiveQuarterCarInstance* comp) {
    fmi2Real x[4] = {comp->z_s, comp->v_s, comp->z_u, comp->v_u};
    fmi2Real dxdt[4];
    fmi2Real ddz_s = 0.0;
    compute_derivatives(comp, x, dxdt, &ddz_s);

    comp->susp_travel = comp->z_s - comp->z_u;
    comp->tire_load_dynamic = comp->k_t * (comp->z_u - comp->z_road) + comp->c_t * (comp->v_u - comp->dz_road);
    comp->body_accel = ddz_s;
    comp->power_act = comp->f_act * (comp->v_s - comp->v_u);
}

static void rk4_step(ActiveQuarterCarInstance* comp, fmi2Real h) {
    fmi2Real x0[4] = {comp->z_s, comp->v_s, comp->z_u, comp->v_u};
    fmi2Real k1[4], k2[4], k3[4], k4[4];
    fmi2Real xtmp[4];
    int i;

    /* k1 */
    compute_derivatives(comp, x0, k1, NULL);

    /* k2 */
    for (i = 0; i < 4; i++) xtmp[i] = x0[i] + 0.5 * h * k1[i];
    compute_derivatives(comp, xtmp, k2, NULL);

    /* k3 */
    for (i = 0; i < 4; i++) xtmp[i] = x0[i] + 0.5 * h * k2[i];
    compute_derivatives(comp, xtmp, k3, NULL);

    /* k4 */
    for (i = 0; i < 4; i++) xtmp[i] = x0[i] + h * k3[i];
    compute_derivatives(comp, xtmp, k4, NULL);

    /* Update state */
    for (i = 0; i < 4; i++) {
        x0[i] += (h / 6.0) * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i]);
    }

    comp->z_s = x0[0];
    comp->v_s = x0[1];
    comp->z_u = x0[2];
    comp->v_u = x0[3];
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
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
    (void)nCategories; (void)categories;
    if (!comp) return fmi2Fatal;
    comp->loggingOn = loggingOn;
    return fmi2OK;
}

FMI2_Export fmi2Component fmi2Instantiate(fmi2String instanceName, fmi2Type fmuType,
                                         fmi2String fmuGUID, fmi2String fmuResourceLocation,
                                         const fmi2CallbackFunctions* functions,
                                         fmi2Boolean visible, fmi2Boolean loggingOn) {
    ActiveQuarterCarInstance* comp;
    (void)fmuType; (void)fmuResourceLocation; (void)visible;

    if (!functions || !functions->allocateMemory || !functions->freeMemory) {
        return NULL;
    }
    if (strcmp(fmuGUID, MODEL_GUID) != 0) {
        return NULL;
    }

    comp = (ActiveQuarterCarInstance*)functions->allocateMemory(1, sizeof(ActiveQuarterCarInstance));
    if (!comp) return NULL;
    memset(comp, 0, sizeof(ActiveQuarterCarInstance));

    /* Default physical parameters */
    comp->m_s = 300.0;
    comp->m_u = 40.0;
    comp->k_s = 25000.0;
    comp->c = 1500.0;
    comp->k_t = 190000.0;
    comp->MR = 1.0;
    comp->c_t = 0.0;

    /* Inputs */
    comp->z_road = 0.0;
    comp->dz_road = 0.0;
    comp->f_act = 0.0;

    /* States */
    comp->z_s = 0.0;
    comp->v_s = 0.0;
    comp->z_u = 0.0;
    comp->v_u = 0.0;

    comp->time = 0.0;
    comp->state = MODEL_STATE_INSTANTIATED;
    strncpy(comp->instanceName, instanceName ? instanceName : "ActiveQuarterCar", sizeof(comp->instanceName) - 1);
    comp->callbacks = functions;
    comp->loggingOn = loggingOn;

    update_outputs(comp);
    return (fmi2Component)comp;
}

FMI2_Export void fmi2FreeInstance(fmi2Component c) {
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
    if (comp && comp->callbacks && comp->callbacks->freeMemory) {
        comp->callbacks->freeMemory(comp);
    }
}

FMI2_Export fmi2Status fmi2SetupExperiment(fmi2Component c, fmi2Boolean toleranceDefined,
                                          fmi2Real tolerance, fmi2Real startTime,
                                          fmi2Boolean stopTimeDefined, fmi2Real stopTime) {
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
    (void)toleranceDefined; (void)tolerance; (void)stopTimeDefined; (void)stopTime;
    if (!comp) return fmi2Fatal;
    comp->time = startTime;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2EnterInitializationMode(fmi2Component c) {
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->state = MODEL_STATE_INITIALIZATION_MODE;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2ExitInitializationMode(fmi2Component c) {
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->state = MODEL_STATE_STEP_MODE;
    update_outputs(comp);
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2Terminate(fmi2Component c) {
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->state = MODEL_STATE_TERMINATED;
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2Reset(fmi2Component c) {
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
    if (!comp) return fmi2Fatal;
    comp->z_s = 0.0;
    comp->v_s = 0.0;
    comp->z_u = 0.0;
    comp->v_u = 0.0;
    comp->z_road = 0.0;
    comp->dz_road = 0.0;
    comp->f_act = 0.0;
    comp->time = 0.0;
    comp->state = MODEL_STATE_INSTANTIATED;
    update_outputs(comp);
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2GetReal(fmi2Component c, const fmi2ValueReference vr[],
                                  size_t nvr, fmi2Real value[]) {
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
    size_t i;
    if (!comp || !vr || !value) return fmi2Fatal;

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
            case VR_F_ACT:              value[i] = comp->f_act; break;
            case VR_Z_S:                value[i] = comp->z_s; break;
            case VR_V_S:                value[i] = comp->v_s; break;
            case VR_Z_U:                value[i] = comp->z_u; break;
            case VR_V_U:                value[i] = comp->v_u; break;
            case VR_SUSP_TRAVEL:        value[i] = comp->susp_travel; break;
            case VR_TIRE_LOAD_DYNAMIC:  value[i] = comp->tire_load_dynamic; break;
            case VR_BODY_ACCEL:         value[i] = comp->body_accel; break;
            case VR_POWER_ACT:          value[i] = comp->power_act; break;
            case VR_TIME:               value[i] = comp->time; break;
            default:
                return fmi2Error;
        }
    }
    return fmi2OK;
}

FMI2_Export fmi2Status fmi2SetReal(fmi2Component c, const fmi2ValueReference vr[],
                                  size_t nvr, const fmi2Real value[]) {
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
    size_t i;
    if (!comp || !vr || !value) return fmi2Fatal;

    for (i = 0; i < nvr; i++) {
        switch (vr[i]) {
            case VR_M_S:     comp->m_s = value[i]; break;
            case VR_M_U:     comp->m_u = value[i]; break;
            case VR_K_S:     comp->k_s = value[i]; break;
            case VR_C:       comp->c = value[i]; break;
            case VR_K_T:     comp->k_t = value[i]; break;
            case VR_MR:      comp->MR = value[i]; break;
            case VR_C_T:     comp->c_t = value[i]; break;
            case VR_Z_ROAD:  comp->z_road = value[i]; break;
            case VR_DZ_ROAD: comp->dz_road = value[i]; break;
            case VR_F_ACT:   comp->f_act = value[i]; break;
            case VR_Z_S:     comp->z_s = value[i]; break;
            case VR_V_S:     comp->v_s = value[i]; break;
            case VR_Z_U:     comp->z_u = value[i]; break;
            case VR_V_U:     comp->v_u = value[i]; break;
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
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
    fmi2Real remaining_h;
    fmi2Real dt_sub;
    (void)noSetFMUStatePriorToCurrentPoint;

    if (!comp) return fmi2Fatal;
    if (comp->state != MODEL_STATE_STEP_MODE) return fmi2Error;
    if (communicationStepSize <= 0.0) return fmi2Error;

    comp->time = currentCommunicationPoint;
    remaining_h = communicationStepSize;

    /* High-precision sub-stepping (maximum sub-step: 0.2 ms) */
    while (remaining_h > 1e-12) {
        dt_sub = remaining_h > 0.0002 ? 0.0002 : remaining_h;
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
    ActiveQuarterCarInstance* comp = (ActiveQuarterCarInstance*)c;
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

/* State serialization / rollback support (stubs returning discarded if unsupported) */
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
