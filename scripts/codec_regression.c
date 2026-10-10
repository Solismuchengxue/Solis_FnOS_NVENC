/* 小型 CPU 编解码探针。SCFIX3 是测试专用 packet/extradata 格式，不是影音容器。 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libavcodec/avcodec.h>
#include <libavutil/imgutils.h>
#include <libavutil/opt.h>
#include <libavutil/sha.h>

static void require(int ok, const char *message) {
    if (!ok) { fprintf(stderr, "PROBE_ERROR: %s\n", message); exit(1); }
}
static void checked(int status, const char *message) {
    if (status < 0) { char error[128]; av_strerror(status, error, sizeof(error));
        fprintf(stderr, "PROBE_ERROR: %s: %s\n", message, error); exit(1); }
}
static void digest_file(const char *path, char text[65]) {
    FILE *file = fopen(path, "rb"); require(file != NULL, "hash input open");
    struct AVSHA *sha = av_sha_alloc(); require(sha != NULL, "sha allocation");
    checked(av_sha_init(sha, 256), "sha init");
    uint8_t buffer[65536], digest[32]; size_t count;
    while ((count = fread(buffer, 1, sizeof(buffer), file))) av_sha_update(sha, buffer, count);
    require(!ferror(file), "hash input read"); fclose(file); av_sha_final(sha, digest); av_free(sha);
    for (int i = 0; i < 32; i++) snprintf(text + i * 2, 3, "%02x", digest[i]);
}
static void identity(void) {
    Dl_info info; char actual[PATH_MAX], expected[PATH_MAX], hash[65];
    const char *path = getenv("EXPECTED_LIB"), *wanted = getenv("EXPECTED_SHA");
    require(path && wanted, "explicit expected library identity required");
    require(dladdr((void *)avcodec_version, &info) != 0, "dladdr avcodec_version");
    require(realpath(info.dli_fname, actual) && realpath(path, expected), "resolve loaded library");
    require(!strcmp(actual, expected), "loaded libavcodec path mismatch");
    digest_file(actual, hash); require(!strcmp(hash, wanted), "loaded libavcodec hash mismatch");
    require(avcodec_version() == AV_VERSION_INT(62, 28, 101), "codec API version mismatch");
    fprintf(stderr, "LOADED_LIB=%s\nLOADED_SHA256=%s\n", actual, hash);
    FILE *maps = fopen("/proc/self/maps", "r"); require(maps != NULL, "process maps");
    char line[4096]; while (fgets(line, sizeof(line), maps))
        if (strstr(line, "libavcodec.so")) fprintf(stderr, "LIB_MAP=%s", line);
    fclose(maps);
}
static void put32(FILE *file, uint32_t value) {
    uint8_t bytes[4] = {value, value >> 8, value >> 16, value >> 24};
    require(fwrite(bytes, 1, 4, file) == 4, "fixture write");
}
static uint32_t get32(FILE *file) {
    uint8_t b[4]; require(fread(b, 1, 4, file) == 4, "fixture truncated header");
    return b[0] | (uint32_t)b[1] << 8 | (uint32_t)b[2] << 16 | (uint32_t)b[3] << 24;
}
static void packets(AVCodecContext *context, AVFrame *frame, AVPacket *packet, FILE *file, int *count) {
    checked(avcodec_send_frame(context, frame), "send encode frame");
    int status;
    while ((status = avcodec_receive_packet(context, packet)) >= 0) {
        require(packet->size > 0 && packet->size < 1048576, "bounded encoded packet");
        put32(file, packet->size); require(fwrite(packet->data, 1, packet->size, file) == (size_t)packet->size, "packet write");
        (*count)++; av_packet_unref(packet);
    }
    require(status == AVERROR(EAGAIN) || status == AVERROR_EOF, "receive encode packet");
}
static void generate(const char *name, const char *path, int channels, int profile) {
    const AVCodec *codec = avcodec_find_encoder_by_name(name); require(codec != NULL, "encoder unavailable");
    AVCodecContext *context = avcodec_alloc_context3(codec); require(context != NULL, "encoder allocation");
    context->thread_count = 1; context->strict_std_compliance = FF_COMPLIANCE_EXPERIMENTAL;
    context->profile = profile; context->flags |= AV_CODEC_FLAG_GLOBAL_HEADER;
    const int video = codec->type == AVMEDIA_TYPE_VIDEO;
    if (video) {
        context->width = 144; context->height = 96; context->pix_fmt = AV_PIX_FMT_YUV420P;
        context->time_base = (AVRational){1, 24}; context->framerate = (AVRational){24, 1};
        context->bit_rate = 300000; context->gop_size = 24; context->max_b_frames = 2;
        if (!strcmp(name, "libx264")) checked(av_opt_set(context->priv_data, "preset", "medium", 0), "x264 preset");
        if (!strcmp(name, "libx265")) checked(av_opt_set(context->priv_data, "x265-params", "pools=none:frame-threads=1:log-level=error", 0), "x265 parameters");
    } else {
        const void *formats = NULL;
        checked(avcodec_get_supported_config(context, codec, AV_CODEC_CONFIG_SAMPLE_FORMAT, 0, &formats, NULL), "supported sample formats");
        require(formats != NULL, "sample format list"); context->sample_fmt = ((const enum AVSampleFormat *)formats)[0];
        context->sample_rate = 48000; context->time_base = (AVRational){1, 48000};
        av_channel_layout_default(&context->ch_layout, channels);
        if (!strcmp(name, "dca") && channels == 6) {
            av_channel_layout_uninit(&context->ch_layout);
            context->ch_layout = (AVChannelLayout)AV_CHANNEL_LAYOUT_5POINT1;
        }
        context->bit_rate = !strcmp(name, "dca") ? 768000 : (!strcmp(name, "libfdk_aac") ? 64000 : (channels > 2 ? 384000 : 128000));
    }
    checked(avcodec_open2(context, codec, NULL), "encoder open");
    AVCodecParameters *parameters = avcodec_parameters_alloc(); require(parameters != NULL, "parameters allocation");
    checked(avcodec_parameters_from_context(parameters, context), "encode parameters");
    FILE *file = fopen(path, "wbx"); require(file != NULL, "new fixture required");
    require(fwrite("SCFIX3\0", 1, 8, file) == 8, "fixture magic");
    put32(file, parameters->codec_id); put32(file, parameters->codec_type);
    put32(file, parameters->codec_tag);
    put32(file, parameters->width); put32(file, parameters->height); put32(file, parameters->format);
    put32(file, parameters->sample_rate); put32(file, parameters->ch_layout.nb_channels);
    require(video || parameters->ch_layout.order == AV_CHANNEL_ORDER_NATIVE, "fixture native channel layout");
    put32(file, parameters->ch_layout.u.mask); put32(file, parameters->ch_layout.u.mask >> 32);
    put32(file, parameters->bits_per_coded_sample); put32(file, parameters->block_align);
    put32(file, parameters->bit_rate); put32(file, parameters->profile); put32(file, parameters->extradata_size);
    require(fwrite(parameters->extradata, 1, parameters->extradata_size, file) == (size_t)parameters->extradata_size, "extradata write");
    AVFrame *frame = av_frame_alloc(); AVPacket *packet = av_packet_alloc(); require(frame && packet, "encode frame/packet allocation");
    frame->format = video ? context->pix_fmt : context->sample_fmt;
    frame->width = context->width; frame->height = context->height;
    frame->sample_rate = context->sample_rate; frame->nb_samples = context->frame_size;
    checked(av_channel_layout_copy(&frame->ch_layout, &context->ch_layout), "frame channel layout");
    checked(av_frame_get_buffer(frame, 32), "frame buffer");
    int count = 0, frames = video ? 48 : (96000 + context->frame_size - 1) / context->frame_size;
    for (int n = 0; n < frames; n++) {
        checked(av_frame_make_writable(frame), "writable frame");
        if (video) {
            for (int y = 0; y < frame->height; y++) for (int x = 0; x < frame->width; x++)
                frame->data[0][y * frame->linesize[0] + x] = 16 + ((x * 3 + y * 2 + n * 7) % 220);
            for (int p = 1; p < 3; p++) for (int y = 0; y < frame->height / 2; y++) for (int x = 0; x < frame->width / 2; x++)
                frame->data[p][y * frame->linesize[p] + x] = 32 + ((x * 2 + y + n * 3 + p * 37) % 192);
            frame->pts = n;
        } else {
            enum AVSampleFormat packed = av_get_packed_sample_fmt(context->sample_fmt);
            int planar = av_sample_fmt_is_planar(context->sample_fmt), bytes = av_get_bytes_per_sample(context->sample_fmt);
            for (int i = 0; i < frame->nb_samples; i++) for (int ch = 0; ch < channels; ch++) {
                int frequency = channels == 6 && ch == 3 ? 60 : 440 + ch * 110;
                double value = 0.2 * sin(2 * M_PI * frequency * ((int64_t)n * frame->nb_samples + i) / 48000.0);
                uint8_t *dest = frame->extended_data[planar ? ch : 0] + (planar ? i : i * channels + ch) * bytes;
                if (packed == AV_SAMPLE_FMT_S16) { int16_t v = value * 32767; memcpy(dest, &v, 2); }
                else if (packed == AV_SAMPLE_FMT_S32) { int32_t v = value * 2147483647; memcpy(dest, &v, 4); }
                else if (packed == AV_SAMPLE_FMT_FLT) { float v = value; memcpy(dest, &v, 4); }
                else require(0, "unsupported synthetic encoder sample format");
            }
            frame->pts = (int64_t)n * frame->nb_samples;
        }
        packets(context, frame, packet, file, &count);
    }
    packets(context, NULL, packet, file, &count); put32(file, 0); require(fclose(file) == 0, "fixture close");
    printf("{\"mode\":\"generate\",\"encoder\":\"%s\",\"frames\":%d,\"packets\":%d,\"sample_rate\":%d,\"channels\":%d,\"profile\":%d}\n", name, frames, count, context->sample_rate, channels, context->profile);
    av_frame_free(&frame); av_packet_free(&packet); avcodec_parameters_free(&parameters); avcodec_free_context(&context);
}
struct Stats { int frames, channels, rate, width, height, format; int64_t samples, bytes; double square, peak; int minimum, maximum; };
static double sample(const uint8_t *data, enum AVSampleFormat format) {
    if (format == AV_SAMPLE_FMT_U8) return (*data - 128) / 128.0;
    if (format == AV_SAMPLE_FMT_S16) { int16_t v; memcpy(&v, data, 2); return v / 32768.0; }
    if (format == AV_SAMPLE_FMT_S32) { int32_t v; memcpy(&v, data, 4); return v / 2147483648.0; }
    if (format == AV_SAMPLE_FMT_S64) { int64_t v; memcpy(&v, data, 8); return v / 9223372036854775808.0; }
    if (format == AV_SAMPLE_FMT_FLT) { float v; memcpy(&v, data, 4); return v; }
    if (format == AV_SAMPLE_FMT_DBL) { double v; memcpy(&v, data, 8); return v; }
    require(0, "unsupported decoded sample format"); return 0;
}
static void receive(AVCodecContext *context, AVFrame *frame, FILE *output, struct Stats *stats) {
    int status;
    while ((status = avcodec_receive_frame(context, frame)) >= 0) {
        require(!frame->decode_error_flags, "decoded frame error flag"); stats->frames++; stats->format = frame->format;
        if (context->codec_type == AVMEDIA_TYPE_VIDEO) {
            stats->width = frame->width; stats->height = frame->height;
            int size = av_image_get_buffer_size(frame->format, frame->width, frame->height, 1); checked(size, "pixel buffer size");
            uint8_t *data = av_malloc(size); require(data != NULL, "pixel allocation");
            checked(av_image_copy_to_buffer(data, size, (const uint8_t *const *)frame->data, frame->linesize, frame->format, frame->width, frame->height, 1), "canonical pixels");
            for (int i = 0; i < size; i++) { if (data[i] < stats->minimum) stats->minimum = data[i]; if (data[i] > stats->maximum) stats->maximum = data[i]; }
            require(fwrite(data, 1, size, output) == (size_t)size, "pixel write"); stats->bytes += size; av_free(data);
        } else {
            stats->channels = frame->ch_layout.nb_channels; stats->rate = frame->sample_rate; stats->samples += frame->nb_samples;
            int planar = av_sample_fmt_is_planar(frame->format), bytes = av_get_bytes_per_sample(frame->format);
            enum AVSampleFormat format = av_get_packed_sample_fmt(frame->format);
            for (int i = 0; i < frame->nb_samples; i++) for (int ch = 0; ch < stats->channels; ch++) {
                const uint8_t *source = frame->extended_data[planar ? ch : 0] + (planar ? i : i * stats->channels + ch) * bytes;
                float value = sample(source, format); require(isfinite(value), "nonfinite PCM");
                stats->square += (double)value * value; if (fabs(value) > stats->peak) stats->peak = fabs(value);
                require(fwrite(&value, 4, 1, output) == 1, "PCM write"); stats->bytes += 4;
            }
        }
        av_frame_unref(frame);
    }
    require(status == AVERROR(EAGAIN) || status == AVERROR_EOF, "receive decoded frame");
}
static void decode(const char *name, const char *path, const char *out) {
    FILE *file = fopen(path, "rb"); require(file != NULL, "fixture input"); char magic[8];
    require(fread(magic, 1, 8, file) == 8 && !memcmp(magic, "SCFIX3\0", 8), "fixture format");
    AVCodecParameters *p = avcodec_parameters_alloc(); require(p != NULL, "decode parameters allocation");
    p->codec_id = get32(file); p->codec_type = get32(file); p->codec_tag = get32(file);
    p->width = get32(file); p->height = get32(file); p->format = get32(file);
    p->sample_rate = get32(file); int channels = get32(file); require(channels >= 0 && channels <= 8, "fixture channel bound");
    uint64_t mask = get32(file); mask |= (uint64_t)get32(file) << 32;
    if (channels) { checked(av_channel_layout_from_mask(&p->ch_layout, mask), "fixture layout mask"); require(p->ch_layout.nb_channels == channels, "fixture channel mask count"); }
    p->bits_per_coded_sample = get32(file); p->block_align = get32(file);
    p->bit_rate = get32(file); p->profile = (int32_t)get32(file); p->extradata_size = get32(file);
    require(p->extradata_size >= 0 && p->extradata_size <= 65536, "fixture extradata bound");
    p->extradata = av_mallocz(p->extradata_size + AV_INPUT_BUFFER_PADDING_SIZE); require(p->extradata != NULL, "extradata allocation");
    require(fread(p->extradata, 1, p->extradata_size, file) == (size_t)p->extradata_size, "extradata read");
    const AVCodec *codec = avcodec_find_decoder_by_name(name); require(codec && codec->id == p->codec_id, "matching decoder required");
    AVCodecContext *context = avcodec_alloc_context3(codec); require(context != NULL, "decoder allocation");
    checked(avcodec_parameters_to_context(context, p), "decode parameters"); context->thread_count = 1; context->err_recognition = AV_EF_EXPLODE;
    checked(avcodec_open2(context, codec, NULL), "decoder open");
    FILE *output = fopen(out, "wbx"); require(output != NULL, "new output required");
    AVPacket *packet = av_packet_alloc(); AVFrame *frame = av_frame_alloc(); require(packet && frame, "decode packet/frame allocation");
    struct Stats stats = {.minimum = 255}; int count = 0;
    for (;;) {
        uint32_t size = get32(file); if (!size) break;
        require(size <= 1048576 && count++ < 4096, "fixture packet/count bound");
        checked(av_new_packet(packet, size), "decode packet allocation");
        require(fread(packet->data, 1, size, file) == size, "packet read");
        checked(avcodec_send_packet(context, packet), "send decode packet"); receive(context, frame, output, &stats); av_packet_unref(packet);
    }
    require(fgetc(file) == EOF && !ferror(file), "fixture trailing bytes/read failure");
    checked(avcodec_send_packet(context, NULL), "flush decoder"); receive(context, frame, output, &stats);
    require(fclose(output) == 0, "output close"); fclose(file); require(stats.frames > 0 && stats.bytes > 0, "empty decoded output");
    char hash[65]; digest_file(out, hash);
    printf("{\"mode\":\"decode\",\"decoder\":\"%s\",\"packets\":%d,\"frames\":%d,\"samples\":%lld,\"sample_rate\":%d,\"channels\":%d,\"width\":%d,\"height\":%d,\"format\":%d,\"bytes\":%lld,\"sha256\":\"%s\",\"rms\":%.12g,\"peak\":%.12g,\"pixel_min\":%d,\"pixel_max\":%d}\n", name, count, stats.frames, (long long)stats.samples, stats.rate, stats.channels, stats.width, stats.height, stats.format, (long long)stats.bytes, hash, stats.samples ? sqrt(stats.square / (stats.samples * stats.channels)) : 0, stats.peak, stats.minimum, stats.maximum);
    av_packet_free(&packet); av_frame_free(&frame); avcodec_parameters_free(&p); avcodec_free_context(&context);
}
static void import_ac4(const char *path, const char *out) {
    FILE *file = fopen(path, "rb"); require(file != NULL, "AC4 input open");
    uint8_t *input = av_mallocz(1048576 + AV_INPUT_BUFFER_PADDING_SIZE); require(input != NULL, "AC4 input allocation");
    size_t size = fread(input, 1, 1048576, file);
    require(size > 0 && size < 1048576 && !ferror(file) && fgetc(file) == EOF, "AC4 input size bound"); fclose(file);
    AVCodecParserContext *parser = av_parser_init(AV_CODEC_ID_AC4); require(parser != NULL, "AC4 parser available");
    const AVCodec *codec = avcodec_find_decoder(AV_CODEC_ID_AC4); require(codec != NULL, "AC4 decoder available");
    AVCodecContext *context = avcodec_alloc_context3(codec); require(context != NULL, "AC4 parser context");
    FILE *output = fopen(out, "wbx"); require(output != NULL, "new AC4 fixture required");
    require(fwrite("SCFIX3\0", 1, 8, output) == 8, "AC4 fixture magic");
    const uint32_t fields[15] = {AV_CODEC_ID_AC4, AVMEDIA_TYPE_AUDIO, 0, 0, 0, (uint32_t)-1, 0, 0, 0, 0, 0, 0, 0, (uint32_t)-99, 0};
    for (int i = 0; i < 15; i++) put32(output, fields[i]);
    size_t offset = 0; int packets_count = 0;
    if (size >= 10 && !memcmp(input, "ID3", 3)) {
        require((input[3] == 3 || input[3] == 4) && input[5] == 0, "supported leading ID3 tag");
        size_t tag = 0;
        for (int i = 6; i < 10; i++) { require(!(input[i] & 128), "ID3 synchsafe length"); tag = (tag << 7) | input[i]; }
        offset = 10 + tag; require(offset < size, "bounded leading ID3 tag");
    }
    size_t tag_bytes = offset;
    /* 固定上游 raw AC4 demuxer 的帧边界：sync + 16/24-bit payload size + optional CRC。
     * 本补丁 parser 只分析单个 payload，不负责 elementary stream 拆帧。
     */
    while (offset < size) {
        require(size - offset >= 4 && input[offset] == 0xac && (input[offset + 1] == 0x40 || input[offset + 1] == 0x41), "AC4 sync frame");
        size_t header = 4, payload = (size_t)input[offset + 2] << 8 | input[offset + 3];
        const size_t crc = input[offset + 1] == 0x41 ? 2 : 0;
        if (payload == 65535) {
            require(size - offset >= 7, "AC4 extended size header"); header = 7;
            payload = (size_t)input[offset + 4] << 16 | (size_t)input[offset + 5] << 8 | input[offset + 6];
        }
        require(payload > 0 && payload <= size - offset - header && crc <= size - offset - header - payload, "AC4 complete frame bound");
        uint8_t *packet = NULL; int bytes = 0;
        int consumed = av_parser_parse2(parser, context, &packet, &bytes, input + offset + header, payload, AV_NOPTS_VALUE, AV_NOPTS_VALUE, offset);
        checked(consumed, "AC4 payload analysis");
        require(consumed == (int)payload && bytes == (int)payload && packets_count++ < 1024, "AC4 single payload parser contract");
        put32(output, bytes); require(fwrite(packet, 1, bytes, output) == (size_t)bytes, "AC4 packet write");
        offset += header + payload + crc;
    }
    require(offset == size && packets_count > 0, "AC4 parser complete input");
    put32(output, 0); require(fclose(output) == 0, "AC4 fixture close");
    printf("{\"mode\":\"import-ac4\",\"input_bytes\":%zu,\"id3_bytes\":%zu,\"packets\":%d,\"codec_id\":%d}\n", size, tag_bytes, packets_count, AV_CODEC_ID_AC4);
    av_parser_close(parser); avcodec_free_context(&context); av_free(input);
}
int main(int argc, char **argv) {
    if (argc != 6 || (strcmp(argv[1], "generate") && strcmp(argv[1], "decode") && strcmp(argv[1], "import-ac4"))) return 64;
    identity(); av_log_set_level(AV_LOG_WARNING);
    if (!strcmp(argv[1], "generate")) generate(argv[2], argv[3], atoi(argv[4]), atoi(argv[5]));
    else if (!strcmp(argv[1], "decode")) decode(argv[2], argv[3], argv[4]);
    else import_ac4(argv[2], argv[3]);
    return 0;
}
