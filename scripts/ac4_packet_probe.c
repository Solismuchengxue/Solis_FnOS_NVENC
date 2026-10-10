/* Strict demux consumer: packet identity, clean EOF, nonzero on malformed input. */
#include <stdio.h>
#include <libavformat/avformat.h>
#include <libavutil/sha.h>
#include <libavutil/mem.h>
int main(int argc, char **argv) {
    AVFormatContext *s = avformat_alloc_context();
    AVPacket *p = av_packet_alloc();
    struct AVSHA *sha = av_sha_alloc();
    unsigned char digest[32];
    int ret, count = 0;
    if (argc != 2 || !s || !p || !sha) return 64;
    s->flags |= AVFMT_FLAG_NOPARSE;
    ret = avformat_open_input(&s, argv[1], av_find_input_format("ac4"), NULL);
    if (ret < 0) goto done;
    while ((ret = av_read_frame(s, p)) >= 0) {
        if (p->size <= 0) { ret = AVERROR_INVALIDDATA; break; }
        av_sha_init(sha, 256); av_sha_update(sha, p->data, p->size); av_sha_final(sha, digest);
        printf("%lld\t%d\t", (long long)p->pos, p->size);
        for (int i = 0; i < 32; i++) printf("%02x", digest[i]);
        putchar('\n'); count++; av_packet_unref(p);
    }
done:
    fprintf(stderr, "packets=%d ret=%d\n", count, ret);
    av_packet_free(&p); av_free(sha); avformat_close_input(&s);
    return ret == AVERROR_EOF && count ? 0 : 1;
}
