/* SCFIX3 独立实现对照：仅链接 FDK AAC / VideoLAN libdca，不链接 FFmpeg。
 * 私人诊断驱动；不是标准符合性或长期质量认证。
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fdk-aac/aacdecoder_lib.h>
#include <dca.h>

static void need(int ok, const char *message) {
    if (!ok) { fprintf(stderr, "REFERENCE_ERROR: %s\n", message); exit(1); }
}
static uint32_t read32(FILE *file) {
    uint8_t b[4]; need(fread(b, 1, 4, file) == 4, "truncated fixture");
    return b[0] | (uint32_t)b[1] << 8 | (uint32_t)b[2] << 16 | (uint32_t)b[3] << 24;
}
static void identity(const char *mode) {
    Dl_info info; char loaded[PATH_MAX], expected[PATH_MAX];
    const char *path = getenv("EXPECTED_REFERENCE_LIB"); need(path != NULL, "explicit reference path required");
    void *symbol = !strcmp(mode, "aac") ? (void *)aacDecoder_Open : (void *)dca_init;
    need(dladdr(symbol, &info) && realpath(info.dli_fname, loaded) && realpath(path, expected), "reference resolution");
    need(!strcmp(loaded, expected), "reference path mismatch");
    fprintf(stderr, "REFERENCE_LIB=%s\n", loaded);
    FILE *maps = fopen("/proc/self/maps", "r"); need(maps != NULL, "reference maps");
    char line[4096];
    while (fgets(line, sizeof(line), maps)) {
        need(strstr(line, "libavcodec") == NULL && strstr(line, "libavutil") == NULL, "FFmpeg mapped in independent reference");
        if (strstr(line, "libfdk-aac") || strstr(line, "libdca")) fprintf(stderr, "REFERENCE_MAP=%s", line);
    }
    fclose(maps);
}
static void write_pcm(FILE *out, float value) {
    need(isfinite(value), "reference nonfinite PCM"); need(fwrite(&value, 4, 1, out) == 1, "reference PCM write");
}
int main(int argc, char **argv) {
    if (argc != 4 || (strcmp(argv[1], "aac") && strcmp(argv[1], "dts"))) return 64;
    identity(argv[1]);
    FILE *file = fopen(argv[2], "rb"); need(file != NULL, "fixture input");
    char magic[8]; need(fread(magic, 1, 8, file) == 8 && !memcmp(magic, "SCFIX3\0", 8), "SCFIX3 required");
    uint32_t fields[15]; for (int i = 0; i < 15; i++) fields[i] = read32(file);
    need(fields[1] == 1 && fields[7] >= 1 && fields[7] <= 6 && fields[14] <= 65536, "audio fixture parameters");
    uint8_t *extra = calloc(fields[14] + 1, 1); need(extra != NULL, "extradata allocation");
    need(fread(extra, 1, fields[14], file) == fields[14], "extradata read");
    const int aac = !strcmp(argv[1], "aac");
    HANDLE_AACDECODER faac = NULL; dca_state_t *dts = NULL;
    if (aac) {
        faac = aacDecoder_Open(TT_MP4_RAW, 1); need(faac != NULL && fields[14] > 0, "AAC raw decoder");
        UINT size = fields[14]; need(aacDecoder_ConfigRaw(faac, &extra, &size) == AAC_DEC_OK, "AAC AudioSpecificConfig");
        need(aacDecoder_SetParam(faac, AAC_PCM_LIMITER_ENABLE, 0) == AAC_DEC_OK, "disable AAC limiter");
        need(aacDecoder_SetParam(faac, AAC_CONCEAL_METHOD, 1) == AAC_DEC_OK, "AAC interpolation setting");
    } else { dts = dca_init(0); need(dts != NULL, "DTS state"); }
    FILE *out = fopen(argv[3], "wbx"); need(out != NULL, "new reference output required");
    int packets = 0, frames = 0, channels = 0, rate = 0; int64_t samples = 0;
    for (;;) {
        uint32_t size = read32(file); if (!size) break;
        need(size <= 1048576 && packets++ < 4096, "reference packet bounds");
        uint8_t *packet = calloc(size + 64, 1); need(packet != NULL, "packet allocation");
        need(fread(packet, 1, size, file) == size, "packet read");
        if (aac) {
            UINT valid = size, capacity = size; UCHAR *cursor = packet;
            need(aacDecoder_Fill(faac, &cursor, &capacity, &valid) == AAC_DEC_OK && valid == 0, "AAC complete packet fill");
            INT_PCM pcm[8 * 4096];
            AAC_DECODER_ERROR status = aacDecoder_DecodeFrame(faac, pcm, 8 * 4096, 0);
            if (status != AAC_DEC_OK) fprintf(stderr, "AAC_STATUS=0x%x\n", status);
            need(status == AAC_DEC_OK, "AAC decode; no concealed output accepted");
            CStreamInfo *info = aacDecoder_GetStreamInfo(faac);
            need(info && info->numChannels > 0 && info->numChannels <= 8 && info->frameSize > 0 && info->frameSize <= 4096, "AAC output bounds");
            need(sizeof(INT_PCM) == 2, "reference INT_PCM is s16");
            if (!frames) fprintf(stderr, "AAC_STREAM=aot:%d,extAot:%d,coreChannels:%d,outputChannels:%d,delay:%u\n", info->aot, info->extAot, info->aacNumChannels, info->numChannels, info->outputDelay);
            else need(channels == info->numChannels && rate == info->sampleRate, "AAC stable output configuration");
            channels = info->numChannels; rate = info->sampleRate;
            for (int i = 0; i < info->frameSize * channels; i++) write_pcm(out, pcm[i] / 32768.0f);
            samples += info->frameSize; frames++;
        } else {
            int flags, sr, br, length;
            int bytes = dca_syncinfo(dts, packet, &flags, &sr, &br, &length);
            need(bytes == (int)size && length > 0, "DTS complete frame");
            int mode = flags & DCA_CHANNEL_MASK;
            need(mode == DCA_STEREO || (mode == DCA_3F2R && (flags & DCA_LFE)), "DTS supported stereo/5.1 core mode");
            level_t level = 1.0f;
            need(dca_frame(dts, packet, &flags, &level, 0) == 0, "DTS frame decode"); dca_dynrng(dts, NULL, NULL);
            int nc = mode == DCA_STEREO ? 2 : 6;
            if (frames) need(channels == nc && rate == sr, "DTS stable output configuration");
            channels = nc; rate = sr;
            int blocks = dca_blocks_num(dts); need(blocks > 0 && blocks <= 16 && blocks * 256 == length, "DTS block bounds");
            /* libdca 3F2R planar order C,L,R,SL,SR,LFE -> canonical L,R,C,LFE,SL,SR. */
            const int mapping[6] = {1, 2, 0, 5, 3, 4};
            for (int b = 0; b < blocks; b++) {
                need(dca_block(dts) == 0, "DTS block decode"); sample_t *pcm = dca_samples(dts); need(pcm != NULL, "DTS samples");
                for (int i = 0; i < 256; i++) for (int ch = 0; ch < channels; ch++)
                    write_pcm(out, pcm[(channels == 6 ? mapping[ch] : ch) * 256 + i]);
                samples += 256; frames++;
            }
        }
        free(packet);
    }
    need(fgetc(file) == EOF && !ferror(file), "fixture trailing bytes");
    need(fclose(out) == 0 && frames > 0, "reference nonempty output"); fclose(file);
    printf("{\"reference\":\"%s\",\"packets\":%d,\"frames\":%d,\"samples\":%lld,\"sample_rate\":%d,\"channels\":%d,\"flush\":\"none; steady-state comparison only\"}\n", aac ? "fdk-aac" : "libdca", packets, frames, (long long)samples, rate, channels);
    if (faac) aacDecoder_Close(faac);
    if (dts) dca_free(dts);
    free(extra);
    return 0;
}
