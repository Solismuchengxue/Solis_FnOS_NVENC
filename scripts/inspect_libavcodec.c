/* 只枚举版本、codec 注册与 descriptor；不初始化 GPU 或处理媒体。 */
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include "libavcodec/codec.h"
#include "libavcodec/codec_desc.h"
#include "libavcodec/version.h"

int main(int argc, char **argv) {
    if (argc != 2) return 64;
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 65; }
    unsigned (*version)(void) = dlsym(library, "avcodec_version");
    const AVCodec *(*iterate)(void **) = dlsym(library, "av_codec_iterate");
    int (*encoder)(const AVCodec *) = dlsym(library, "av_codec_is_encoder");
    int (*decoder)(const AVCodec *) = dlsym(library, "av_codec_is_decoder");
    const AVCodecDescriptor *(*descriptor_next)(const AVCodecDescriptor *) = dlsym(library, "avcodec_descriptor_next");
    if (!version || !iterate || !encoder || !decoder || !descriptor_next) return 66;
    if (version() != AV_VERSION_INT(62, 28, 101)) return 67;
    printf("VERSION\t62.28.101\n");
    void *state = NULL;
    const AVCodec *codec;
    while ((codec = iterate(&state))) {
        if (encoder(codec)) printf("ENCODER\t%s\t%d\n", codec->name, codec->id);
        if (decoder(codec)) printf("DECODER\t%s\t%d\n", codec->name, codec->id);
    }
    const AVCodecDescriptor *descriptor = NULL;
    while ((descriptor = descriptor_next(descriptor))) {
        printf("DESCRIPTOR\t%d\t%s\n", descriptor->id, descriptor->name);
    }
    dlclose(library);
    return 0;
}
